#!/usr/bin/env python3

import unittest

from migen import *

from litex.soc.cores.gpio import GPIOOut

from ..endpoint import *
from ..io import FakeIoBuf
from ..pid import PIDTypes
from ..rx.pipeline import RxPipeline
from ..tx.pipeline import TxPipeline
from .header import PacketHeaderDecode
from .send import TxPacketSend

from ..utils.packet import *
from ..test.common import CommonUsbTestCase
from ..test.clock import CommonTestMultiClockDomain


class UsbTransfer(Module):
    def __init__(self, iobuf, auto_crc=True):
        self.submodules.iobuf = iobuf

        self.submodules.tx = tx = TxPipeline()
        self.submodules.txstate = txstate = TxPacketSend(tx, auto_crc=auto_crc)

        self.submodules.rx = rx = RxPipeline()
        self.submodules.rxstate = rxstate = PacketHeaderDecode(rx)

        # ----------------------
        # USB 48MHz bit strobe
        # ----------------------
        self.comb += [
            tx.i_bit_strobe.eq(rx.o_bit_strobe),
        ]

        self.reset = Signal()

        # ----------------------
        # Data paths
        # ----------------------
        self.data_recv_put = Signal()
        self.data_recv_payload = Signal(8)

        self.data_send_get = Signal()
        self.data_send_have = Signal()
        self.data_send_payload = Signal(8)

        # ----------------------
        # State signally
        # ----------------------
        # The value of these signals are generally dependent on endp, so we
        # need to wait for the rdy signal to use them.
        self.rdy = Signal(reset=1)
        self.dtb = Signal()
        self.arm = Signal()
        self.sta = Signal()

        # ----------------------
        # Tristate
        # ----------------------
        self.submodules.iobuf = iobuf
        self.comb += [
            rx.i_usbp.eq(iobuf.usb_p_rx),
            rx.i_usbn.eq(iobuf.usb_n_rx),
            iobuf.usb_tx_en.eq(tx.o_oe),
            iobuf.usb_p_tx.eq(tx.o_usbp),
            iobuf.usb_n_tx.eq(tx.o_usbn),
        ]
        self.submodules.pullup = GPIOOut(iobuf.usb_pullup)

        self.tok    = Signal(4)    # Contains the transfer token type
        self.addr   = Signal(7)
        self.endp   = Signal(4)

        self.start  = Signal()     # Asserted when a transfer is starting
        self.setup  = Signal()     # Asserted when a transfer is a setup
        self.commit = Signal()     # Asserted when a transfer succeeds
        self.abort  = Signal()     # Asserted when a transfer fails
        self.end    = Signal()     # Asserted when transfer ends
        self.comb += [
            self.end.eq(self.commit | self.abort),
        ]

        # Host->Device data path (Out + Setup data path)
        #
        # Token
        # Data
        # Handshake
        #
        # Setup --------------------
        # >Setup
        # >Data0[bmRequestType, bRequest, wValue, wIndex, wLength]
        # <Ack
        # --------------------------
        #
        # Data ---------------------
        # >Out        >Out        >Out
        # >DataX[..]  >DataX[..]  >DataX
        # <Ack        <Nak        <Stall
        #
        # Status -------------------
        # >Out
        # >Data0[]
        # <Ack
        # ---------------------------
        #
        # Host<-Device data path (In data path)
        # --------------------------
        # >In         >In     >In
        # <DataX[..]  <Stall  <Nak
        # >Ack
        # ---------------------------
        # >In
        # <Data0[]
        # >Ack
        # ---------------------------
        transfer = FSM(reset_state="WAIT_TOKEN")
        self.submodules.transfer = transfer = ClockDomainsRenamer("usb_12")(transfer)
        transfer.act("ERROR",
            If(self.reset, NextState("WAIT_TOKEN")),
        )

        transfer.act("WAIT_TOKEN",
            If(rx.o_pkt_start,
                NextState("RECV_TOKEN"),
            ),
        )

        transfer.act("RECV_TOKEN",
            If(rxstate.o_decoded,
                #If((rxstate.o_pid & PIDTypes.TYPE_MASK) != PIDTypes.TOKEN,
                #    NextState('ERROR'),
                #),
                NextValue(self.tok,  rxstate.o_pid),
                NextValue(self.addr, rxstate.o_addr),
                NextValue(self.endp, rxstate.o_endp),
                self.start.eq(1),
                NextState("POLL_RESPONSE"),
            ),
        )

        response_pid = Signal(4)
        transfer.act("POLL_RESPONSE",
            If(self.rdy,
                # Work out the response
                If(self.tok == PID.SETUP,
                    NextValue(response_pid, PID.ACK),
                ).Elif(self.sta,
                    NextValue(response_pid, PID.STALL),
                ).Elif(self.arm,
                    NextValue(response_pid, PID.ACK),
                ).Else(
                    NextValue(response_pid, PID.NAK),
                ),

                # Setup transfer
                If(self.tok == PID.SETUP,
                    NextState("WAIT_DATA"),

                # Out transfer
                ).Elif(self.tok == PID.OUT,
                    NextState("WAIT_DATA"),

                # In transfer
                ).Elif(self.tok == PID.IN,
                    If(~self.arm | self.sta,
                        NextState("SEND_HAND"),
                    ).Else(
                        NextState("SEND_DATA"),
                    ),
                ).Else(
                    NextState("WAIT_TOKEN"),
                ),
            ),
        )

        # Out + Setup pathway
        transfer.act("WAIT_DATA",
            If(rxstate.o_decoded,
                If((rxstate.o_pid & PIDTypes.TYPE_MASK) == PIDTypes.DATA,
                    NextState('RECV_DATA'),
                ).Else(
                    NextState('ERROR'),
                )
            ),
        )

        transfer.act("RECV_DATA",
            If(response_pid == PID.ACK,
                self.data_recv_put.eq(rx.o_data_strobe),
            ),
            If(rx.o_pkt_end,
                NextState("SEND_HAND"),
            ),
        )
        self.comb += [
            self.data_recv_payload.eq(rx.o_data_payload),
        ]

        # In pathway
        transfer.act("SEND_DATA",
            self.data_send_get.eq(txstate.o_data_ack),
            If(txstate.o_pkt_end, NextState("WAIT_HAND")),
        )
        self.comb += [
            txstate.i_data_payload.eq(self.data_send_payload),
            txstate.i_data_ready.eq(self.data_send_have),
        ]

        # Handshake
        transfer.act("WAIT_HAND",
            If(rxstate.o_decoded,
                self.commit.eq(1),
                # Host can't reject?
                If((rxstate.o_pid & PIDTypes.TYPE_MASK) == PIDTypes.HANDSHAKE,
                    NextState('WAIT_TOKEN'),
                ).Else(
                    NextState('ERROR'),
                )
            ),
        )
        transfer.act("SEND_HAND",
            If(txstate.o_pkt_end,
                self.setup.eq(self.tok == PID.SETUP),
                If(response_pid == PID.ACK,
                    self.commit.eq(1),
                ).Else(
                    self.abort.eq(1),
                ),
                NextState("WAIT_TOKEN"),
            ),
        )

        # Code to reset header decoder when entering the WAIT_XXX states.
        self.comb += [
            If(tx.o_oe,
                rx.reset.eq(1),
            ),
        ]
        # Code to initiate the sending of packets when entering the SEND_XXX
        # states.
        self.comb += [
            If(transfer.after_entering("SEND_DATA"),
                If(self.dtb,
                    txstate.i_pid.eq(PID.DATA1),
                ).Else(
                    txstate.i_pid.eq(PID.DATA0),
                ),
                txstate.i_pkt_start.eq(1),
            ),
            If(transfer.after_entering("SEND_HAND"),
                txstate.i_pid.eq(response_pid),
                txstate.i_pkt_start.eq(1),
            ),
        ]


class TestUsbTransaction(CommonUsbTestCase, CommonTestMultiClockDomain):

    maxDiff=None

    def setUp(self):
        CommonTestMultiClockDomain.setUp(self, ("usb_12", "usb_48"))

        self.iobuf = FakeIoBuf()
        self.dut = UsbTransfer(self.iobuf)

        self.packet_h2d = Signal(1)
        self.packet_d2h = Signal(1)
        self.packet_idle = Signal(1)

        class Endpoint:
            def __init__(self):
                self._response = EndpointResponse.NAK
                self.trigger = False
                self.pending = True
                self.data = None
                self.dtb = True

            def update(self):
                if self.trigger:
                    self.pending = True

            @property
            def response(self):
                if self._response == EndpointResponse.ACK and (self.pending or self.trigger):
                    return EndpointResponse.NAK
                else:
                    return self._response

            @response.setter
            def response(self, v):
                assert isinstance(v, EndpointResponse), repr(v)
                self._response = v

            def __str__(self):
                data = self.data
                if data is None:
                    data = []
                return "<Endpoint p:(%s,%s) %s d:%s>" % (
                    int(self.trigger), int(self.pending), int(self.dtb), len(data))

        self.endpoints = {
            EndpointType.epaddr(0, EndpointType.OUT): Endpoint(),
            EndpointType.epaddr(0, EndpointType.IN):  Endpoint(),
            EndpointType.epaddr(1, EndpointType.OUT): Endpoint(),
            EndpointType.epaddr(1, EndpointType.IN):  Endpoint(),
            EndpointType.epaddr(2, EndpointType.OUT): Endpoint(),
            EndpointType.epaddr(2, EndpointType.IN):  Endpoint(),
        }
        for epaddr in self.endpoints:
            self.endpoints[epaddr].addr = epaddr

    def run_sim(self, stim):
        def padfront():
            yield self.packet_h2d.eq(0)
            yield self.packet_d2h.eq(0)
            yield self.packet_idle.eq(0)
            yield
            yield
            yield
            yield from self.dut.pullup._out.write(1)
            yield
            yield
            yield
            yield
            yield from self.idle()
            yield from stim()

        print()
        print("-"*10)
        run_simulation(
            self.dut,
            padfront(),
            vcd_name=self.make_vcd_name(),
            clocks={"sys": 12, "usb_48": 48, "usb_12": 192},
        )
        print("-"*10)

    def tick_usb(self):
        yield from self.wait_for_edge("usb_48")

    def on_usb_48_edge(self):
        if False:
            yield

    def on_usb_12_edge(self):
        dut = self.dut

        # These should only change on usb12 edge
        start = yield dut.start
        setup = yield dut.setup
        commit = yield dut.commit
        abort = yield dut.abort
        end = yield dut.end

        tok = yield dut.tok
        addr = yield dut.addr
        endp = yield dut.endp

        if endp > 2:
            return

        # -----

        # Host->Device pathway
        oep = self.endpoints[EndpointType.epaddr(endp, EndpointType.OUT)]
        data_recv_put = yield dut.data_recv_put
        if data_recv_put:
            data_recv_payload = yield dut.data_recv_payload
            if oep.data is None:
                oep.data = []
            oep.data.append(data_recv_payload)

        # Host->Device State flags
        if tok == PID.OUT or tok == PID.SETUP:
            if oep.response == EndpointResponse.STALL:
                yield dut.sta.eq(1)
            else:
                yield dut.sta.eq(0)

            if oep.response == EndpointResponse.NAK:
                yield dut.arm.eq(0)
            if oep.response == EndpointResponse.ACK:
                yield dut.arm.eq(1)

            if commit:
                oep.dtb = not oep.dtb
                oep.trigger = True

        # -----

        # Device->Host pathway
        iep = self.endpoints[EndpointType.epaddr(endp, EndpointType.IN)]
        data_send_get = yield dut.data_send_get

        if iep.data:
            yield dut.data_send_payload.eq(iep.data[0])
        else:
            yield dut.data_send_payload.eq(0xff)

        if not iep.pending and iep.data:
            if data_send_get:
                iep.data.pop(0)
            yield dut.data_send_have.eq(len(iep.data) > 0)
        else:
            yield dut.data_send_have.eq(0)
            self.assertFalse(data_send_get)

        # Device->Host State flags
        if tok == PID.IN:
            if iep.response == EndpointResponse.STALL:
                yield dut.sta.eq(1)
            else:
                yield dut.sta.eq(0)

            if iep.response == EndpointResponse.NAK:
                yield dut.arm.eq(0)
            if iep.response == EndpointResponse.ACK:
                yield dut.arm.eq(1)

            yield dut.dtb.eq(iep.dtb)

            if commit:
                iep.dtb = not iep.dtb
                iep.trigger = True

        # -----

        # Special setup stuff...
        if setup:
            oep.response = EndpointResponse.NAK
            oep.dtb = True

            iep.response = EndpointResponse.NAK
            iep.dtb = True

    def update_internal_signals(self):
        for ep in self.endpoints.values():
            if ep.trigger:
                ep.pending = True
                ep.trigger = False
        del ep

        yield from self.update_clocks()

    ######################################################################
    ## Helpers
    ######################################################################

    # IRQ / packet pending -----------------
    def trigger(self, epaddr):
        yield from self.update_internal_signals()
        return self.endpoints[epaddr].trigger

    def pending(self, epaddr):
        yield from self.update_internal_signals()
        return self.endpoints[epaddr].pending or self.endpoints[epaddr].trigger

    def clear_pending(self, epaddr):
        # Can't clear pending while trigger is active.
        trigger = (yield from self.trigger(epaddr))
        #for i in range(0, 100):
        #    trigger = (yield from self.trigger(epaddr))
        #    if not trigger:
        #        break
        #    yield
        self.assertFalse(trigger)

        # Check the pending flag is raised
        self.assertTrue((yield from self.pending(epaddr)))

        # Clear pending flag
        self.endpoints[epaddr].pending = False
        self.ep_print(epaddr, "clear_pending")

        # Check the pending flag has been cleared
        self.assertFalse((yield from self.trigger(epaddr)))
        self.assertFalse((yield from self.pending(epaddr)))

    # Endpoint state -----------------------
    def response(self, epaddr):
        if False:
            yield
        return self.endpoints[epaddr].response

    def set_response(self, epaddr, v):
        assert isinstance(v, EndpointResponse), v
        if False:
            yield
        self.ep_print(epaddr, "set_response: %s", v)
        self.endpoints[epaddr].response = v

    # Get/set endpoint data ----------------
    def set_data(self, epaddr, data):
        """Set an endpoints buffer to given data to be sent."""
        if False:
            yield

        assert isinstance(data, (list, tuple))
        if not isinstance(data, list):
            data = list(data)

        self.ep_print(epaddr, "set_data: %r", data)
        self.endpoints[epaddr].data = data

    def expect_data(self, epaddr, data):
        """Expect that an endpoints buffer has given contents."""
        # Make sure there is something pending
        for i in range(10):
            pending = yield from self.pending(epaddr)
            if pending:
                break
            yield from self.tick_usb()
        self.assertTrue(pending)

        self.ep_print(epaddr, "expect_data: %s", data)
        actual_data = self.endpoints[epaddr].data
        assert actual_data is not None
        self.endpoints[epaddr].data = None

        # Strip the last two bytes which contain the CRC16
        assert len(actual_data) >= 2, actual_data
        actual_data, actual_crc = actual_data[:-2], actual_data[-2:]

        self.ep_print(epaddr, "Got: %r (expected: %r)", actual_data, data)
        self.assertSequenceEqual(data, actual_data)
        self.assertSequenceEqual(crc16(data), actual_crc)

    def dtb(self, epaddr):
        if False:
            yield
        print("dtb", epaddr, self.endpoints[epaddr])
        return self.endpoints[epaddr].dtb



if __name__ == "__main__":
    unittest.main()
