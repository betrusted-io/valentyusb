#!/usr/bin/env python3

from itertools import zip_longest

import CrcMoose3 as crc

import unittest
from unittest import TestCase
from usbcore import *




class TestRxPacketDetect(TestCase):
    def test_packet_detect(self):

        test_vectors = [
            dict(
                # SE0, Idle
                valid    = "------------------------------",
                value    = "______________1111111111111111",
                output_1 = "                               ",
                output_2 = "_______________________________"
            ),

            dict(
                # Idle, Packet, Idle
                valid    = "------------------------------",
                value    = "11111000000011111111101__11111",
                output_1 = "             S          E      ",
                output_2 = "_____________-----------_______"
            ),

            dict(
                # Idle, Packet, Idle (pipeline stall)
                valid    = "-------------___-----------------",
                value    = "11111000000011111111111101__11111",
                output_1 = "             S             E      ",
                output_2 = "_____________--------------_______"
            ),

            dict(
                # Idle, Packet, Idle (pipeline stalls)
                valid    = "-----___---___-----___-----------------",
                value    = "11111111000___000011111111111101__11111",
                output_1 = "                   S             E      ",
                output_2 = "___________________--------------_______"
            ),

            dict(
                # Idle, Packet, Idle, Packet, Idle
                valid    = "------------------------------------------------------------",
                value    = "11111000000011111111101__1111111111000000011111111101__11111",
                output_1 = "             S          E                  S          E      ",
                output_2 = "_____________-----------___________________-----------_______"
            ),

            dict(
                # Idle, Short Sync Packet, Idle
                valid    = "----------------------------",
                value    = "111110000011111111101__11111",
                output_1 = "           S          E      ",
                output_2 = "___________-----------_______"
            ),

            dict(
                # Idle Glitch
                valid    = "------------------------------",
                value    = "11111111110011111111_1111__111",
                output_1 = "                               ",
                output_2 = "_______________________________"
            ),
        ]

        def send(valid, value):
            valid += "_"
            value += "_"
            output_1 = ""
            output_2 = ""
            for i in range(len(valid)):
                yield i_valid.eq(valid[i] == '-')
                yield i_data.eq(value[i] == '1')
                yield i_se0.eq(value[i] == '_')
                yield

                pkt_start = yield dut.o_pkt_start
                pkt_end = yield dut.o_pkt_end

                out = "%d%d" % (pkt_start, pkt_end)

                output_1 += {
                    "10" : "S",
                    "01" : "E",
                    "00" : " ",
                }[out]

                pkt_active = yield dut.o_pkt_active

                out = "%d" % (pkt_active)

                output_2 += {
                    "1" : "-",
                    "0" : "_",
                }[out]

            return output_1, output_2

        def stim(valid, value, output_1, output_2):
            actual_output_1, actual_output_2 = yield from send(valid, value)
            self.assertEqual(actual_output_1, output_1)
            self.assertEqual(actual_output_2, output_2)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_valid = Signal()
                i_data = Signal()
                i_se0 = Signal()

                dut = RxPacketDetect(i_valid, i_data, i_se0)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_packet_det_%d.vcd" % i)
                i += 1



class TestRxPacketDecode(TestCase):
    def test_pkt_decode(self):
        def send(valid, value):
            pid = []
            token_payload = []
            data_payload = []
            data = []
            pkt_good = []
            for i in range(len(valid)):
                yield i_valid.eq(valid[i] == '-')
                yield i_data.eq(value[i] == '1' or value[i] == 'B')
                yield i_se0.eq(value[i] == '_')
                yield i_bitstuff_error.eq(value[i] == 'B')
                yield

                o_pkt_start = yield dut.o_pkt_start
                o_pkt_pid = yield dut.o_pkt_pid
                o_pkt_token_payload = yield dut.o_pkt_token_payload
                o_pkt_data = yield dut.o_pkt_data
                o_pkt_data_put = yield dut.o_pkt_data_put
                o_pkt_good = yield dut.o_pkt_good
                o_pkt_end = yield dut.o_pkt_end

                if o_pkt_data_put:
                    data += [o_pkt_data]

                if o_pkt_end:
                    pid += [o_pkt_pid]
                    token_payload += [o_pkt_token_payload]
                    data_payload.append(data)
                    data = []
                    pkt_good += [o_pkt_good]

            return pid, token_payload, data_payload, pkt_good

        test_vectors = [
            dict(
                # USB2 SOF token
                valid           = "---------------------------------------",
                value           = "1100000001101001011000011011000010__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 SOF token - pipeline stalls
                valid           = "----------_--------_-----------_----------",
                value           = "1100000001_10100101_10000110110_00010__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 SOF token - eop dribble 1
                valid           = "----------_--------_-----------_-----_-----",
                value           = "1100000001_10100101_10000110110_00010_1__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 SOF token - eop dribble 6
                valid           = "----------_--------_-----------_-----_-----------",
                value           = "1100000001_10100101_10000110110_00010_111111__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 SOF token - bad pid
                valid           = "----------_--------_-----------_----------",
                value           = "1100000001_10100100_10000110110_00010__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 SOF token - bad crc5
                valid           = "----------_--------_-----------_----------",
                value           = "1100000001_10100101_10000110110_00011__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 SOF token - bitstuff error
                valid           = "----------_-----_____-_____--_-----------_----------",
                value           = "1100000001_10100_____B_____01_10000110110_00010__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 ACK handshake
                valid           = "----------_-------------",
                value           = "1100000001_01001011__111",
                pid             = [0b0010],
                token_payload   = [0],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 ACK handshake - late bitstuff error
                valid           = "----------_-------------",
                value           = "1100000001_0100101B__111",
                pid             = [0b0010],
                token_payload   = [0],
                data_payload    = [[]],
                pkt_good        = [0]
            ),


            dict(
                # USB2 ACK handshake - pid error
                valid           = "----------_-------------",
                value           = "1100000001_01001111__111",
                pid             = [0b0010],
                token_payload   = [0],
                data_payload    = [[]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 ACK handshake - EOP dribble 1
                valid           = "----------_--------_-----",
                value           = "1100000001_01001011_1__111",
                pid             = [0b0010],
                token_payload   = [0],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 ACK handshake - EOP dribble 6
                valid           = "----------_--------_-----------",
                value           = "1100000001_01001011_111111__111",
                pid             = [0b0010],
                token_payload   = [1792], # token payload doesn't matter in this test, but dribble triggers it
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 data with good CRC16 (1)
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 data with good CRC16 - 1 eop dribble
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_-_-----",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001_1___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 data with good CRC16 - 6 eop dribble
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------_------",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001_111111___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [1]
            ),

            # TODO: need a better way to handle eop dribble with bitstuff error :(
            #dict(
            #    # USB2 data with good CRC16 - 1 eop dribble with bitstuff error
            #    valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_-_-----",
            #    value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001_B___1111",
            #    pid             = [0b0011],
            #    token_payload   = [1664], # token payload is a "don't care" for this test
            #    data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
            #    pkt_good        = [1]
            #),

            #dict(
            #    # USB2 data with good CRC16 - 6 eop dribble with bitstuff error
            #    valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------_------",
            #    value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001_11111B___1111",
            #    pid             = [0b0011],
            #    token_payload   = [1664], # token payload is a "don't care" for this test
            #    data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
            #    pkt_good        = [1]
            #),

            dict(
                # USB2 data with bad CRC16 (1)
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101011___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0xD4]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 data with late bitstuff error
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_0010100B___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 data with bad pid
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value       = "1100000001_11000001_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 SETUP and DATA
                valid           = "----------_--------_-----------_----------___---------------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value           = "1100000001_10110100_00000000000_01000__111___111111100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001___1111",
                pid             = [0b1101,  0b0011],
                token_payload   = [0,       1664],
                data_payload    = [[],      [0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [1,       1]
            ),
        ]


        def stim(valid, value, pid, token_payload, data_payload, pkt_good):
            actual_pid, actual_token_payload, actual_data_payload, actual_pkt_good = yield from send(valid, value)
            self.assertEqual(actual_pid, pid)
            self.assertEqual(actual_token_payload, token_payload)
            self.assertEqual(actual_data_payload, data_payload)
            self.assertEqual(actual_pkt_good, pkt_good)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_valid = Signal()
                i_data = Signal()
                i_se0 = Signal()
                i_bitstuff_error = Signal()

                dut = RxPacketDecode(
                    i_valid,
                    i_data,
                    i_se0,
                    i_bitstuff_error)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_decode_%d.vcd" % i)
            i += 1





class TestUsbFsTx_longer(TestCase):
    def do(self, clocks, pid, token_payload, data, expected_output):
        self.output = ""
        name = self.id()

        # create dut
        i_bit_strobe = Signal(1)
        i_pkt_start = Signal(1)
        i_pid = Signal(4)
        i_token_payload = Signal(11)
        i_data_valid = Signal(1)
        i_data_payload = Signal(8)

        dut = UsbFsTx(i_bit_strobe, i_pkt_start, i_pid, i_token_payload, i_data_valid, i_data_payload)

        def clock():
            yield i_data_valid.eq(len(data) > 0)
            if len(data) > 0:
                yield i_data_payload.eq(data[0])
            else:
                yield i_data_payload.eq(0)

            yield

            o_data_get = yield dut.o_data_get
            if o_data_get:
                data.pop(0)

            oe = yield dut.o_oe
            usbp = yield dut.o_usbp
            usbn = yield dut.o_usbn

            if oe == 0:
                self.output += " "
            else:
                if usbp == 0 and usbn == 0:
                    self.output += "_"
                elif usbp == 1 and usbn == 0:
                    self.output += "j"
                elif usbp == 0 and usbn == 1:
                    self.output += "k"
                else:
                    self.output += "!"

        # setup stimulus
        def stim():
            # initiate packet transmission
            yield i_pid.eq(pid)
            yield i_token_payload.eq(token_payload)
            yield i_pkt_start.eq(1)

            yield from clock()

            yield i_pid.eq(0)
            yield i_token_payload.eq(0)
            yield i_pkt_start.eq(0)

            # pump the clock and collect output
            for i in range(clocks):
                yield i_bit_strobe.eq(1)

                yield from clock()

                yield i_bit_strobe.eq(0)

                yield from clock()
                yield from clock()
                yield from clock()

            import re
            m = re.fullmatch(idle() + expected_output + idle(), self.output)
            if m:
                pass
            else:
                raise AssertionError("Packet not found:\n    %s\n    %s" % (expected_output, self.output))


        # run simulation
        run_simulation(dut, stim(), vcd_name="vcd/%s.vcd" % name)


    def test_ack_handshake(self):
        self.do(
            clocks          = 100,
            pid             = PID.ACK,
            token_payload   = 0,
            data            = [],
            expected_output = nrzi(sync() + encode_pid(PID.ACK) + eop())
        )

    def test_empty_data(self):
        self.do(
            clocks          = 100,
            pid             = PID.DATA0,
            token_payload   = 0,
            data            = [],
            expected_output = nrzi(sync() + encode_pid(PID.DATA0) + encode_data([0x00, 0x00]) + eop())
        )

    def test_setup_data(self):
        payload = [0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00]

        self.do(
            clocks          = 200,
            pid             = PID.SETUP,
            token_payload   = 0,
            data            = payload,
            expected_output = nrzi(sync() + encode_pid(PID.SETUP) + encode_data(payload + crc16(payload)) + eop())
        )

    def test_setup_data_bitstuff(self):
        payload = [0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x3F]
        self.do(
            clocks          = 200,
            pid             = PID.SETUP,
            token_payload   = 0,
            data            = payload,
            expected_output = nrzi(sync() + encode_pid(PID.SETUP) + encode_data([0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40]) + "111111000" + encode_data(crc16(payload)) + eop())
        )


# one out transaction
# >token, >dataX, <ack

# one in transaction
# >token, <dataX, <ack

# one setup transaction
# >token, >data0, <ack

# setup stage (pid:setup, pid:data0 - 8 bytes, pid:ack)
# [data stage (pid:in+pid:data1, pid:in +pid:data0, ...)]
# status stage (pid:out, pid:data1 - 0 bytes)


# DATA0 and DATA1 PIDs are used in Low and Full speed links as part of an error-checking system.
# When used, all data packets on a particular endpoint use an alternating DATA0
# / DATA1 so that the endpoint knows if a received packet is the one it is
# expecting.
# If it is not it will still acknowledge (ACK) the packet as it is correctly
# received, but will then discard the data, assuming that it has been
# re-sent because the host missed seeing the ACK the first time it sent the
# data packet.


# 1) reset,
#
# 2) The host will now send a request to endpoint 0 of device address 0 to find
#    out its maximum packet size. It can discover this by using the Get
#    Descriptor (Device) command. This request is one which the device must
#    respond to even on address 0.
#
# 3) Then sends a Set Address request, with a unique address to the device at
#    address 0. After the request is completed, the device assumes the new
#    address.
#
#

import tempfile
import subprocess


def grouper(n, iterable, pad=None):
    """Group iterable into multiples of n (with optional padding).

    >>> list(grouper(3, 'abcdefg', 'x'))
    [('a', 'b', 'c'), ('d', 'e', 'f'), ('g', 'x', 'x')]

    """
    return zip_longest(*[iter(iterable)]*n, fillvalue=pad)


class CommonUsbTestCase(TestCase):
    maxDiff=None

    def assertMultiLineEqualSideBySide(self, data1, data2, msg):
        if data1 == data2:
            return
        f1 = tempfile.NamedTemporaryFile()
        f1.write(data1.encode('utf-8'))
        f1.flush()

        f2 = tempfile.NamedTemporaryFile()
        f2.write(data2.encode('utf-8'))
        f2.flush()

        p = subprocess.Popen(["sdiff", f1.name, f2.name], stdout=subprocess.PIPE)
        stdout, stderr = p.communicate()
        diff = stdout.decode('utf-8')

        f1.close()
        f2.close()
        assert False, msg+'\n'+diff

    def ep_print(self, epaddr, msg, *args):
        print("ep(%i, %s): %s" % (
            EndpointType.epnum(epaddr),
            EndpointType.epdir(epaddr).name,
            msg) % args)

    def idle(self, cycles=10):
        yield self.packet_idle.eq(1)
        yield from self.dut.iobuf.recv('I')
        for i in range(0, cycles):
            yield
        yield self.packet_idle.eq(0)

    # Host->Device
    def _send_packet(self, packet):
        """Send a USB packet."""
        #print("_send_packet(", packet, ")")
        packet = wrap_packet(packet)
        for v in packet:
            yield from self._update_internal_signals()
            yield from self.dut.iobuf.recv(v)
            yield
        yield from self._update_internal_signals()
        yield

    def send_token_packet(self, pid, addr, epaddr):
        epnum = EndpointType.epnum(epaddr)
        yield self.packet_h2d.eq(1)
        yield from self._send_packet(token_packet(pid, addr, epnum))
        yield self.packet_h2d.eq(0)

    def send_data_packet(self, pid, data):
        assert pid in (PID.DATA0, PID.DATA1), pid
        yield self.packet_h2d.eq(1)
        yield from self._send_packet(data_packet(pid, data))
        yield self.packet_h2d.eq(0)

    def send_ack(self):
        yield self.packet_h2d.eq(1)
        yield from self._send_packet(handshake_packet(PID.ACK))
        yield self.packet_h2d.eq(0)

    def send_nak(self):
        yield self.packet_h2d.eq(1)
        yield from self._send_packet(handshake_packet(PID.NAK))
        yield self.packet_h2d.eq(0)

    # Device->Host
    def expect_packet(self, packet, msg=None):
        """Except to receive the following USB packet."""
        yield self.packet_d2h.eq(1)

        # Wait for transmission to happen
        yield from self.dut.iobuf.recv('I')
        tx = 0
        for i in range(0, 100):
            yield from self._update_internal_signals()
            tx = yield self.dut.iobuf.usb_tx_en
            if tx:
                break
            yield
        self.assertTrue(tx, "No packet started, "+msg)

        # Read in the packet data
        result = ""
        for i in range(0, 2048):
            yield from self._update_internal_signals()

            result += yield from self.iobuf.current()
            yield
            tx = yield self.dut.iobuf.usb_tx_en
            if not tx:
                break
        self.assertFalse(tx, "Packet didn't finish, "+msg)
        yield self.packet_d2h.eq(0)

        # Check the packet received matches
        expected = pp_packet(wrap_packet(packet))
        actual = pp_packet(result)
        self.assertMultiLineEqualSideBySide(expected, actual, msg)

    # No expect_token_packet, as the host is the only one who generates tokens.

    def expect_data_packet(self, pid, data):
        assert pid in (PID.DATA0, PID.DATA1), pid
        yield self.packet_d2h.eq(1)
        yield from self.expect_packet(data_packet(pid, data), "Expected %s packet with %r" % (pid.name, data))
        yield self.packet_d2h.eq(0)

    def expect_ack(self):
        yield self.packet_d2h.eq(1)
        yield from self.expect_packet(handshake_packet(PID.ACK), "Expected ACK packet.")
        yield self.packet_d2h.eq(0)

    def expect_nak(self):
        yield self.packet_d2h.eq(1)
        yield from self.expect_packet(handshake_packet(PID.NAK), "Expected NAK packet.")
        yield self.packet_d2h.eq(0)

    def expect_stall(self):
        yield self.packet_d2h.eq(1)
        yield from self.expect_packet(handshake_packet(PID.STALL), "Expected STALL packet.")
        yield self.packet_d2h.eq(0)

    def expect_last_tok(self, epaddr, value):
        if False:
            yield

    def check_pending(self, epaddr):
        # Check no pending packets
        self.assertFalse((yield from self.pending(epaddr)))

    def check_pending_and_response(self, epaddr):
        yield from self.check_pending(epaddr)
        # Check we are going to ack the packets
        self.assertEqual((yield from self.response(epaddr)), EndpointResponse.ACK)

    # Full transactions
    # ->token  ->token
    # <-data   ->data
    # ->ack    <-ack

    # Host to Device
    # ->setup
    # ->data0[...]
    # <-ack
    def transaction_setup(self, addr, data):
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)

        yield from self.send_token_packet(PID.SETUP, addr, epaddr_out)
        yield from self.send_data_packet(PID.DATA0, data)
        yield from self.expect_ack()
        yield from self.expect_data(epaddr_out, data)
        yield from self.clear_pending(epaddr_out)

        # Check nothing pending at the end
        self.assertFalse((yield from self.pending(epaddr_out)))

        # Check the token is set correctly
        yield from self.expect_last_tok(epaddr_out, 0b11)

        # Check the in/out endpoint is reset to NAK
        self.assertEqual((yield from self.response(epaddr_out)), EndpointResponse.NAK)
        self.assertEqual((yield from self.response(epaddr_in)), EndpointResponse.NAK)

    # Host to Device
    # ->out
    # ->data0[...]
    # <-ack
    # ->out
    # ->data1[...]
    # <-ack
    # ....
    def transaction_data_out(self, addr, epaddr, data, chunk_size=8):
        yield from self.check_pending_and_response(epaddr)

        datax = PID.DATA0
        for i, chunk in enumerate(grouper(chunk_size, data, pad=0)):
            self.assertFalse((yield from self.pending(epaddr)))
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(datax, chunk)
            yield from self.expect_ack()
            yield from self.expect_data(epaddr, chunk)
            yield from self.clear_pending(epaddr)

            yield from self.expect_last_tok(epaddr, 0b00)
            if datax == PID.DATA0:
                datax = PID.DATA1
            else:
                datax = PID.DATA0

        # Check nothing pending at the end
        self.assertFalse((yield from self.pending(epaddr)))

    # Host to Device
    # ->out
    # ->data1[]
    # <-ack
    def transaction_status_out(self, addr, epaddr):
        assert EndpointType.epdir(epaddr) == EndpointType.OUT
        yield from self.check_pending_and_response(epaddr)

        yield from self.send_token_packet(PID.OUT, addr, epaddr)
        yield from self.send_data_packet(PID.DATA1, [])
        yield from self.expect_ack()
        yield from self.expect_data(epaddr, [])
        yield from self.clear_pending(epaddr)

        # Check nothing pending at the end
        self.assertFalse((yield from self.pending(epaddr)))

    # Device to Host
    # ->in
    # <-data0[...]
    # ->ack
    # ->in
    # <-data1[...]
    # ->ack
    # ....
    def transaction_data_in(self, addr, epaddr, data, chunk_size=8, dtb=PID.DATA1):
        assert EndpointType.epdir(epaddr) == EndpointType.IN

        datax = dtb
        for i, chunk in enumerate(grouper(chunk_size, data, pad=0)):
            yield from self.check_pending_and_response(epaddr)
            yield from self.set_response(epaddr, EndpointResponse.NAK)
            yield from self.set_data(epaddr, chunk)
            yield from self.set_response(epaddr, EndpointResponse.ACK)

            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_data_packet(datax, chunk)
            yield from self.send_ack()
            yield from self.clear_pending(epaddr)

            yield from self.expect_last_tok(epaddr, 0b10)
            if datax == PID.DATA0:
                datax = PID.DATA1
            else:
                datax = PID.DATA0

        # Check nothing pending at the end
        self.assertFalse((yield from self.pending(epaddr)))

    # Device to Host
    # ->in
    # <-data1[]
    # ->ack
    def transaction_status_in(self, addr, epaddr):
        assert EndpointType.epdir(epaddr) == EndpointType.IN
        yield from self.check_pending_and_response(epaddr)

        yield from self.set_data(epaddr, [])
        yield from self.send_token_packet(PID.IN, addr, epaddr)
        yield from self.expect_data_packet(PID.DATA1, [])
        yield from self.send_ack()
        yield from self.clear_pending(epaddr)

        # Check nothing pending at the end
        self.assertFalse((yield from self.pending(epaddr)))

    # Full control transfer
    ########################
    def control_transfer_in(self, addr, setup_data, descriptor_data):
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)

        yield from self.check_pending(epaddr_in)
        yield from self.check_pending(epaddr_out)

        # Setup stage
        yield from self.transaction_setup(addr, setup_data)

        yield from self.check_pending(epaddr_in)
        yield from self.check_pending(epaddr_out)

        # Data stage
        yield from self.set_response(epaddr_in, EndpointResponse.ACK)
        yield from self.transaction_data_in(addr, epaddr_in, descriptor_data)

        yield from self.check_pending(epaddr_in)
        yield from self.check_pending(epaddr_out)

        # Status stage
        yield from self.set_response(epaddr_out, EndpointResponse.ACK)
        yield from self.transaction_status_out(addr, epaddr_out)

        yield from self.check_pending(epaddr_in)
        yield from self.check_pending(epaddr_out)

    def control_transfer_out(self, addr, setup_data, descriptor_data):
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)
        # Setup stage
        yield from self.transaction_setup(addr, setup_data)
        # Data stage
        yield from self.set_response(epaddr_out, EndpointResponse.ACK)
        yield from self.transaction_data_out(addr, epaddr_out, descriptor_data)
        # Status stage
        yield from self.set_response(epaddr_in, EndpointResponse.ACK)
        yield from self.transaction_status_in(addr, epaddr_in)

    ######################################################################
    ######################################################################
    def run_sim(self, stim):
        raise NotImplementedError

    # IRQ / packet pending -----------------
    def trigger(self, epaddr):
        raise NotImplementedError

    def clear_pending(self, epaddr):
        raise NotImplementedError

    def pending(self, epaddr):
        raise NotImplementedError

    # Endpoint state -----------------------
    def response(self, epaddr):
        raise NotImplementedError

    def set_response(self, epaddr, v):
        raise NotImplementedError

    # Get/set endpoint data ----------------
    def set_data(self, epaddr, data):
        raise NotImplementedError

    def expect_data(self, epaddr, data):
        raise NotImplementedError

    ######################################################################
    ######################################################################

    def test_control_setup(self):
        def stim():
            #   012345   0123
            # 0b011100 0b1000
            yield from self.transaction_setup(28, [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00])
        self.run_sim(stim)

    def test_control_setup_clears_stall(self):
        def stim():
            addr = 28
            epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)

            d = [0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8]

            yield from self.clear_pending(epaddr_out)
            yield from self.set_response(epaddr_out, EndpointResponse.ACK)
            yield

            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA0, d[:4])
            yield from self.expect_ack()
            yield from self.expect_data(epaddr_out, d[:4])

            yield from self.set_response(epaddr_out, EndpointResponse.STALL)

            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA0, d[4:])
            yield from self.expect_stall()

            yield from self.send_token_packet(PID.SETUP, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA1, d)
            yield from self.expect_ack()

            yield
            respond = yield from self.response(epaddr_out)
            self.assertEqual(respond, EndpointResponse.NAK)
            yield

            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA0, d[:4])
            yield from self.expect_nak()

        self.run_sim(stim)

    def test_control_transfer_in(self):
        def stim():
            yield from self.clear_pending(EndpointType.epaddr(0, EndpointType.OUT))
            yield from self.clear_pending(EndpointType.epaddr(0, EndpointType.IN))
            yield

            yield from self.control_transfer_in(
                20,
                # Get descriptor, Index 0, Type 03, LangId 0000, wLength 10?
                [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00],
                # 12 byte descriptor, max packet size 8 bytes
                [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                 0x08, 0x09, 0x0A, 0x0B],
            )
        self.run_sim(stim)

    def test_control_transfer_in_nak_data(self):
        def stim():
            addr = 22
            # Get descriptor, Index 0, Type 03, LangId 0000, wLength 64
            setup_data = [0x80, 0x06, 0x00, 0x03, 0x00, 0x00, 0x40, 0x00]
            in_data = [0x04, 0x03, 0x09, 0x04]

            epaddr_in = EndpointType.epaddr(0, EndpointType.IN)
            yield from self.clear_pending(epaddr_in)

            # Setup stage
            # -----------
            yield from self.transaction_setup(addr, setup_data)

            # Data stage
            # -----------
            yield from self.set_response(epaddr_in, EndpointResponse.NAK)
            yield from self.send_token_packet(PID.IN, addr, epaddr_in)
            yield from self.expect_nak()

            yield from self.set_data(epaddr_in, in_data)
            yield from self.set_response(epaddr_in, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, epaddr_in)
            yield from self.expect_data_packet(PID.DATA1, in_data)
            yield from self.send_ack()
            yield from self.clear_pending(epaddr_in)

        self.run_sim(stim)

    def test_control_transfer_in_nak_status(self):
        def stim():
            addr = 20
            setup_data = [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00]
            out_data = [0x00, 0x01]

            epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
            epaddr_in = EndpointType.epaddr(0, EndpointType.IN)
            yield from self.clear_pending(epaddr_out)
            yield from self.clear_pending(epaddr_in)

            # Setup stage
            # -----------
            yield from self.transaction_setup(addr, setup_data)

            # Data stage
            # ----------
            yield from self.set_response(epaddr_out, EndpointResponse.ACK)
            yield from self.transaction_data_out(addr, epaddr_out, out_data)

            # Status stage
            # ----------
            yield from self.set_response(epaddr_in, EndpointResponse.NAK)

            yield from self.send_token_packet(PID.IN, addr, epaddr_in)
            yield from self.expect_nak()

            yield from self.send_token_packet(PID.IN, addr, epaddr_in)
            yield from self.expect_nak()

            yield from self.set_response(epaddr_in, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, epaddr_in)
            yield from self.expect_data_packet(PID.DATA1, [])
            yield from self.send_ack()
            yield from self.clear_pending(epaddr_in)

        self.run_sim(stim)

    def test_control_transfer_out(self):
        def stim():
            yield from self.clear_pending(EndpointType.epaddr(0, EndpointType.OUT))
            yield from self.clear_pending(EndpointType.epaddr(0, EndpointType.IN))
            yield

            yield from self.control_transfer_out(
                20,
                # Get descriptor, Index 0, Type 03, LangId 0000, wLength 10?
                [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00],
                # 12 byte descriptor, max packet size 8 bytes
                [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                 0x08, 0x09, 0x0A, 0x0B],
            )
        self.run_sim(stim)

    def test_control_transfer_out_nak_data(self):
        def stim():
            addr = 20
            setup_data = [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00]
            out_data = [
                0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                0x08, 0x09, 0x0A, 0x0B,
            ]

            epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
            yield from self.clear_pending(epaddr_out)

            # Setup stage
            # -----------
            yield from self.transaction_setup(addr, setup_data)

            # Data stage
            # ----------
            yield from self.set_response(epaddr_out, EndpointResponse.NAK)
            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA1, out_data)
            yield from self.expect_nak()

            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA1, out_data)
            yield from self.expect_nak()

            #for i in range(200):
            #    yield

            yield from self.set_response(epaddr_out, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA1, out_data)
            yield from self.expect_ack()
            yield from self.expect_data(epaddr_out, out_data)
            yield from self.clear_pending(epaddr_out)


        self.run_sim(stim)

    def test_control_transfer_out_nak_status(self):
        def stim():
            addr = 20
            setup_data = [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00]
            descriptor_data = [
                0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                0x08, 0x09, 0x0A, 0x0B,
            ]

            epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
            epaddr_in = EndpointType.epaddr(0, EndpointType.IN)
            yield from self.clear_pending(epaddr_out)
            yield from self.clear_pending(epaddr_in)
            yield

            # Setup stage
            # -----------
            yield from self.transaction_setup(addr, setup_data)

            # Data stage
            # ----------
            yield from self.set_response(epaddr_in, EndpointResponse.ACK)
            yield from self.transaction_data_in(addr, epaddr_in, descriptor_data)

            # Status stage
            # ----------
            yield from self.set_response(epaddr_out, EndpointResponse.NAK)
            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA1, [])
            yield from self.expect_nak()

            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA1, [])
            yield from self.expect_nak()

            yield from self.set_response(epaddr_out, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.OUT, addr, epaddr_out)
            yield from self.send_data_packet(PID.DATA1, [])
            yield from self.expect_ack()
            yield from self.expect_data(epaddr_out, [])
            yield from self.clear_pending(epaddr_out)

        self.run_sim(stim)

    def test_in_transfer(self):
        def stim():
            addr = 28
            epaddr = EndpointType.epaddr(1, EndpointType.IN)

            d = [0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8]

            yield from self.clear_pending(epaddr)
            yield from self.set_response(epaddr, EndpointResponse.NAK)
            yield

            yield from self.set_data(epaddr, d[:4])
            yield from self.set_response(epaddr, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_data_packet(PID.DATA1, d[:4])
            yield from self.send_ack()

            self.assertTrue((yield from self.pending(epaddr)))
            yield from self.set_data(epaddr, d[4:])
            yield from self.clear_pending(epaddr)

            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_data_packet(PID.DATA0, d[4:])
            yield from self.send_ack()

        self.run_sim(stim)

    def test_data_in_byte_1(self):
        def stim():
            addr = 28

            ep1 = EndpointType.epaddr(1, EndpointType.IN)
            yield from self.clear_pending(ep1)
            yield from self.set_response(ep1, EndpointResponse.NAK)

            d1 = [0x1]
            yield from self.set_data(ep1, d1)
            yield from self.set_response(ep1, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, ep1)
            yield from self.expect_data_packet(PID.DATA1, d1)
            yield from self.send_ack()
            yield from self.clear_pending(ep1)

        self.run_sim(stim)

    def test_data_in_byte_2(self):
        def stim():
            addr = 28

            ep1 = EndpointType.epaddr(1, EndpointType.IN)
            yield from self.clear_pending(ep1)
            yield from self.set_response(ep1, EndpointResponse.NAK)

            d1 = [0x2]
            yield from self.set_data(ep1, d1)
            yield from self.set_response(ep1, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, ep1)
            yield from self.expect_data_packet(PID.DATA1, d1)
            yield from self.send_ack()
            yield from self.clear_pending(ep1)

        self.run_sim(stim)

    def test_data_in_byte_a(self):
        def stim():
            addr = 28

            ep1 = EndpointType.epaddr(1, EndpointType.IN)
            yield from self.clear_pending(ep1)
            yield from self.set_response(ep1, EndpointResponse.NAK)

            d1 = [0xa]
            yield from self.set_data(ep1, d1)
            yield from self.set_response(ep1, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, ep1)
            yield from self.expect_data_packet(PID.DATA1, d1)
            yield from self.send_ack()
            yield from self.clear_pending(ep1)

        self.run_sim(stim)

    def test_setup_clears_data_toggle_bit(self):
        def stim():
            addr = 28

            ep0in = EndpointType.epaddr(0, EndpointType.IN)
            yield from self.clear_pending(ep0in)
            yield from self.set_response(ep0in, EndpointResponse.NAK)

            ep0out = EndpointType.epaddr(0, EndpointType.OUT)
            yield from self.clear_pending(ep0out)
            yield from self.set_response(ep0out, EndpointResponse.NAK)
            yield

            # Setup stage
            yield from self.transaction_setup(28, [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00])

            dtbi = yield from self.dtb(ep0in)
            self.assertTrue(dtbi)

            dtbo = yield from self.dtb(ep0out)
            self.assertTrue(dtbo)

            # Data stage
            yield from self.set_response(ep0in, EndpointResponse.ACK)
            yield from self.transaction_data_in(addr, ep0in, [0x1])

            dtbi = yield from self.dtb(ep0in)
            self.assertFalse(dtbi)

            dtbo = yield from self.dtb(ep0out)
            self.assertTrue(dtbo)

            # Status stage
            yield from self.set_response(ep0out, EndpointResponse.ACK)
            yield from self.transaction_status_out(addr, ep0out)

            dtbi = yield from self.dtb(ep0in)
            self.assertFalse(dtbi)

            dtbo = yield from self.dtb(ep0out)
            self.assertFalse(dtbo)

            # Data transfer
            yield from self.set_response(ep0in, EndpointResponse.ACK)
            yield from self.transaction_data_in(addr, ep0in, [0x1], dtb=PID.DATA0)

            dtbi = yield from self.dtb(ep0in)
            self.assertTrue(dtbi)

            dtbo = yield from self.dtb(ep0out)
            self.assertFalse(dtbo)

            # Data transfer
            yield from self.set_response(ep0in, EndpointResponse.ACK)
            yield from self.transaction_data_in(addr, ep0in, [0x2], dtb=PID.DATA1)

            dtbi = yield from self.dtb(ep0in)
            self.assertFalse(dtbi)

            dtbo = yield from self.dtb(ep0out)
            self.assertFalse(dtbo)

            # New setup stage should reset dtb
            yield from self.transaction_setup(28, [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00])

            dtbi = yield from self.dtb(ep0in)
            self.assertTrue(dtbi)

            dtbo = yield from self.dtb(ep0out)
            self.assertTrue(dtbo)

        self.run_sim(stim)

    def test_data_toggle_bit_multiple_endpoints(self):
        def stim():
            addr = 28

            ep1 = EndpointType.epaddr(1, EndpointType.IN)
            yield from self.clear_pending(ep1)
            yield from self.set_response(ep1, EndpointResponse.NAK)
            ep2 = EndpointType.epaddr(2, EndpointType.IN)
            yield from self.clear_pending(ep2)
            yield from self.set_response(ep2, EndpointResponse.NAK)
            yield

            d1 = [0x1]
            yield from self.set_data(ep1, d1)
            yield from self.set_response(ep1, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, ep1)
            yield from self.expect_data_packet(PID.DATA1, d1)
            yield from self.send_ack()
            yield from self.clear_pending(ep1)

            d2 = [0x2]
            yield from self.set_data(ep2, d2)
            yield from self.set_response(ep2, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, ep2)
            yield from self.expect_data_packet(PID.DATA1, d2)
            yield from self.send_ack()
            yield from self.clear_pending(ep2)

            d3 = [0x3]
            yield from self.set_data(ep2, d3)
            yield from self.set_response(ep2, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, ep2)
            yield from self.expect_data_packet(PID.DATA0, d3)
            yield from self.send_ack()
            yield from self.clear_pending(ep2)

            d4 = [0x5]
            yield from self.set_data(ep1, d4)
            yield from self.set_response(ep1, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, ep1)
            yield from self.expect_data_packet(PID.DATA0, d4)
            yield from self.send_ack()
            yield from self.clear_pending(ep1)

        self.run_sim(stim)

    def test_in_transfer_nak(self):
        def stim():
            addr = 28
            epaddr = EndpointType.epaddr(1, EndpointType.IN)

            yield from self.clear_pending(epaddr)
            yield from self.set_response(epaddr, EndpointResponse.NAK)
            yield

            # Device NAK the PID.IN token packet
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_nak()

            # Device NAK the PID.IN token packet a second time
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_nak()

            d1 = [0x1, 0x2, 0x3, 0x4]
            yield from self.set_data(epaddr, d1)
            yield from self.set_response(epaddr, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_data_packet(PID.DATA1, d1)
            yield from self.send_ack()
            yield from self.clear_pending(epaddr)

            # Have data but was asked to NAK
            d2 = [0x5, 0x6, 0x7, 0x8]
            yield from self.set_response(epaddr, EndpointResponse.NAK)
            yield from self.set_data(epaddr, d2)
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_nak()

            # Actually send the data now
            yield from self.set_response(epaddr, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_data_packet(PID.DATA0, d2)
            yield from self.send_ack()
            yield from self.clear_pending(epaddr)

        self.run_sim(stim)

    def test_in_stall(self):
        def stim():
            addr = 28
            epaddr = EndpointType.epaddr(1, EndpointType.IN)

            d = [0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8]

            # While pending, set stall
            self.assertTrue((yield from self.pending(epaddr)))
            yield from self.set_response(epaddr, EndpointResponse.STALL)
            yield from self.set_data(epaddr, d[:4])
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_stall()

            yield from self.set_response(epaddr, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_nak()
            yield from self.clear_pending(epaddr)

            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_data_packet(PID.DATA1, d[:4])
            yield from self.send_ack()
            yield from self.set_data(epaddr, d[4:])
            yield from self.clear_pending(epaddr)

            # While not pending, set stall
            self.assertFalse((yield from self.pending(epaddr)))
            yield from self.set_response(epaddr, EndpointResponse.STALL)
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_stall()

            yield from self.set_response(epaddr, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.IN, addr, epaddr)
            yield from self.expect_data_packet(PID.DATA0, d[4:])
            yield from self.send_ack()
            yield from self.clear_pending(epaddr)

        self.run_sim(stim)

    def test_out_transfer(self):
        def stim():
            addr = 28
            epaddr = EndpointType.epaddr(2, EndpointType.OUT)

            d = [0x41, 0x01]

            yield from self.clear_pending(epaddr)
            yield from self.set_response(epaddr, EndpointResponse.NAK)
            yield

            yield from self.set_response(epaddr, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d)
            yield from self.expect_ack()
            yield from self.expect_data(epaddr, d)

            # Should nak until pending is cleared
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d)
            yield from self.expect_nak()

            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d)
            yield from self.expect_nak()

            # Make sure no extra data turned up
            #yield from self.expect_data(epaddr, [])

            yield from self.clear_pending(epaddr)

            d2 = [0x41, 0x02]
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d2)
            yield from self.expect_ack()
            yield from self.expect_data(epaddr, d2)
            yield from self.clear_pending(epaddr)

        self.run_sim(stim)

    def test_out_transfer_nak(self):
        def stim():
            addr = 28
            epaddr = EndpointType.epaddr(2, EndpointType.OUT)

            d = [0x41, 0x01]

            yield from self.clear_pending(epaddr)
            yield from self.set_response(epaddr, EndpointResponse.NAK)
            yield

            # First nak
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d)
            yield from self.expect_nak()
            pending = yield from self.pending(epaddr)
            self.assertFalse(pending)

            # Second nak
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d)
            yield from self.expect_nak()
            pending = yield from self.pending(epaddr)
            self.assertFalse(pending)

            # Third attempt succeeds
            yield from self.set_response(epaddr, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d)
            yield from self.expect_ack()
            yield from self.expect_data(epaddr, d)
            yield from self.clear_pending(epaddr)

        self.run_sim(stim)

    def test_out_stall(self):
        def stim():
            addr = 28
            epaddr = EndpointType.epaddr(2, EndpointType.OUT)

            d = [0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8]

            # While pending, set stall
            self.assertTrue((yield from self.pending(epaddr)))
            yield from self.set_response(epaddr, EndpointResponse.STALL)
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d[:4])
            yield from self.expect_stall()

            yield from self.set_response(epaddr, EndpointResponse.ACK)
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d[:4])
            yield from self.expect_nak()
            yield from self.clear_pending(epaddr)

            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA1, d[:4])
            yield from self.expect_ack()
            yield from self.expect_data(epaddr, d[:4])
            yield from self.clear_pending(epaddr)

            # While not pending, set stall
            self.assertFalse((yield from self.pending(epaddr)))
            yield from self.set_response(epaddr, EndpointResponse.STALL)
            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA0, d[4:])
            yield from self.expect_stall()

            yield from self.set_response(epaddr, EndpointResponse.ACK)

            yield from self.send_token_packet(PID.OUT, addr, epaddr)
            yield from self.send_data_packet(PID.DATA0, d[4:])
            yield from self.expect_ack()
            yield from self.expect_data(epaddr, d[4:])
            yield from self.clear_pending(epaddr)

        self.run_sim(stim)


class TestUsbDevice(CommonUsbTestCase):

    maxDiff=None

    def setUp(self):
        endpoints=[EndpointType.BIDIR, EndpointType.IN, EndpointType.BIDIR]

        self.iobuf = TestIoBuf()
        self.dut = UsbDevice(self.iobuf, 0, endpoints)

        self.buffers_in  = {}
        self.buffers_out = {}

        buffer_signals_layout = [
            ('head', 8),
            ('size', 32),
        ]

        self.packet_h2d = Signal(1)
        self.packet_d2h = Signal(1)
        self.packet_idle = Signal(1)

        self.buffer_signals = []
        for i, ep in enumerate(endpoints):
            if ep & EndpointType.IN:
                buffer_in_signals = Record(buffer_signals_layout, name="ep_%i_in" % i)
                self.buffers_in[i] = []
            else:
                buffer_in_signals = None

            if ep & EndpointType.OUT:
                buffer_out_signals = Record(buffer_signals_layout, name="ep_%i_out" % i)
                self.buffers_out[i] = []
            else:
                buffer_out_signals = None

            self.buffer_signals.append((buffer_in_signals, buffer_out_signals))

    def run_sim(self, stim):
        def padfront():
            yield from self.idle()
            yield from stim()

        run_simulation(self.dut, padfront(), vcd_name="vcd/%s.vcd" % self.id(), clocks={"sys": 4})

    ######################################################################
    ## Helpers
    ######################################################################
    def _update_internal_signals(self):
        """Set the valid/ready/data signals for each endpoint buffer."""
        for i, (in_signals, out_signals) in enumerate(self.buffer_signals):
            if in_signals:
                # Debugging info
                buffer = self.buffers_in[i]
                if buffer is None:
                    yield in_signals.size.eq(-1)
                else:
                    yield in_signals.size.eq(len(buffer))
                    if len(buffer) > 0:
                        yield in_signals.head.eq(buffer[0])

                # Pull bytes from in buffers to the host
                if not buffer:
                    yield self.dut.endp_ins[i].valid.eq(0)
                else:
                    yield self.dut.endp_ins[i].payload.data.eq(buffer[0])
                    yield self.dut.endp_ins[i].valid.eq(1)

                    ready = yield self.dut.endp_ins[i].ready
                    if ready:
                        buffer.pop(0)

            if out_signals:
                # Debugging info
                buffer = self.buffers_out[i]
                if buffer is None:
                    yield out_signals.size.eq(-1)
                else:
                    yield out_signals.size.eq(len(buffer))
                    if len(buffer) > 0:
                        yield out_signals.head.eq(buffer[-1])

                # Set the ready signal
                if buffer is None:
                    yield self.dut.endp_outs[i].ready.eq(0)
                else:
                    yield self.dut.endp_outs[i].ready.eq(1)

                    # Push bytes received from host into out buffers
                    valid = yield self.dut.endp_outs[i].valid
                    if valid:
                        data = yield self.dut.endp_outs[i].data
                        buffer.append(data)

    def set_data(self, epaddr, data):
        """Set an endpoints buffer to given data to be sent."""
        assert isinstance(data, (list, tuple))
        self.ep_print(epaddr, "Set %i: %r", data)
        self.buffers_in[epaddr].extend(data)
        if False:
            yield

    def expect_data(self, ep, data):
        """Expect that an endpoints buffer has given contents."""
        assert ep in self.buffers_out, self.buffers_out.keys()
        assert self.buffers_out[ep] is not None, "Endpoint currently blocked!"
        self.ep_print(epaddr, "Got: %r (expected: %r)", self.buffers_out[ep], data)
        self.assertSequenceEqual(self.buffers_out[ep], data)
        self.buffers_out[ep].clear()
        if False:
            yield


class TestUsbDeviceCpuInterface(CommonUsbTestCase):

    maxDiff=None

    def setUp(self):
        self.endpoints=[EndpointType.BIDIR, EndpointType.IN, EndpointType.BIDIR]

        self.iobuf = TestIoBuf()
        self.dut = UsbDeviceCpuInterface(self.iobuf, self.endpoints)

        self.packet_h2d = Signal(1)
        self.packet_d2h = Signal(1)
        self.packet_idle = Signal(1)


    def run_sim(self, stim):
        def padfront():
            yield
            yield
            yield
            yield
            yield
            yield
            # Make sure that the endpoints are currently blocked
            ostatus = yield self.dut.ep_0_out.ev.packet.pending
            self.assertTrue(ostatus)
            istatus = yield self.dut.ep_0_in.ev.packet.pending
            self.assertTrue(istatus)
            yield
            yield from self.dut.pullup._out.write(1)
            yield
            # Make sure that the endpoints are currently blocked
            ostatus = yield self.dut.ep_0_out.ev.packet.pending
            self.assertTrue(ostatus)
            istatus = yield self.dut.ep_0_in.ev.packet.pending
            self.assertTrue(istatus)

            yield
            yield from self.idle()
            yield from stim()

        run_simulation(self.dut, padfront(), vcd_name="vcd/%s.vcd" % self.id(), clocks={"usb_48": 4, "sys": 4})

    def _update_internal_signals(self):
        if False:
            yield

    def expect_last_tok(self, epaddr, value):
        endpoint = self.get_endpoint(epaddr)
        last_tok = yield from endpoint.last_tok.read()
        self.assertEqual(last_tok, value)

    ######################################################################
    ## Helpers
    ######################################################################
    def get_endpoint(self, epaddr):
        epdir = EndpointType.epdir(epaddr)
        epnum = EndpointType.epnum(epaddr)
        if epdir == EndpointType.OUT:
            return getattr(self.dut, "ep_%s_out" % epnum)
        elif epdir == EndpointType.IN:
            return getattr(self.dut, "ep_%s_in" % epnum)
        else:
            raise SystemError("Unknown endpoint type: %r" % epdir)

    def pending(self, epaddr):
        endpoint = self.get_endpoint(epaddr)
        status = yield from endpoint.ev.pending.read()
        return bool(status & 0x2)

    def dtb(self, epaddr):
        endpoint = self.get_endpoint(epaddr)
        status = yield from endpoint.dtb.read()
        return bool(status)

    def trigger(self, epaddr):
        endpoint = self.get_endpoint(epaddr)
        status = yield endpoint.ev.packet.trigger
        return bool(status)

    def response(self, epaddr):
        endpoint = self.get_endpoint(epaddr)
        response = yield endpoint.response
        return response

    def set_response(self, epaddr, v):
        endpoint = self.get_endpoint(epaddr)
        assert isinstance(v, EndpointResponse), v
        yield from endpoint.respond.write(v)

    def clear_pending(self, epaddr):
        # Can't clear pending while trigger is active.
        while True:
            trigger = (yield from self.trigger(epaddr))
            if not trigger:
                break
            yield
        # Check the pending flag is raised
        self.assertTrue((yield from self.pending(epaddr)))
        # Clear pending flag
        endpoint = self.get_endpoint(epaddr)
        yield from endpoint.ev.pending.write(0xf)
        yield
        # Check the pending flag has been cleared
        self.assertFalse((yield from self.trigger(epaddr)))
        self.assertFalse((yield from self.pending(epaddr)))

    def set_data(self, epaddr, data):
        """Set an endpoints buffer to given data to be sent."""
        assert isinstance(data, (list, tuple))
        self.ep_print(epaddr, "Set: %r", data)

        endpoint = self.get_endpoint(epaddr)

        # Make sure the endpoint is empty
        empty = yield from endpoint.ibuf_empty.read()
        self.assertTrue(empty)

        # If we are writing multiple bytes of data, need to make sure we are
        # not going to ACK the packet until the data is ready.
        if len(data) > 1:
            response = yield endpoint.response
            self.assertNotEqual(response, EndpointResponse.ACK)

        for v in data:
            yield from endpoint.ibuf_head.write(v)
            yield

        yield
        yield
        yield
        if len(data) > 0:
            empty = yield from endpoint.ibuf_empty.read()
            self.assertFalse(bool(empty))
        else:
            empty = yield from endpoint.ibuf_empty.read()
            self.assertTrue(bool(empty))

    def expect_data(self, epaddr, data):
        """Expect that an endpoints buffer has given contents."""
        endpoint = self.get_endpoint(epaddr)

        # Make sure there is something pending
        self.assertTrue((yield from self.pending(epaddr)))

        actual_data = []
        while range(0, 1024):
            yield from endpoint.obuf_head.write(0)
            empty = yield from endpoint.obuf_empty.read()
            if empty:
                break

            v = yield from endpoint.obuf_head.read()
            actual_data.append(v)
            yield

        self.ep_print(epaddr, "Got: %r (expected: %r)", actual_data, data)
        self.assertSequenceEqual(data, actual_data)


def _get_bit(epaddr, v):
    """
    >>> _get_bit(0, 0b11)
    True
    >>> _get_bit(0, 0b10)
    False
    >>> _get_bit(0, 0b101)
    True
    >>> _get_bit(1, 0b101)
    False
    """
    return bool(1 << epaddr & v)


def _set_bit(current, epaddr, v):
    """
    >>> bin(_set_bit(0, 0, 1))
    '0b1'
    >>> bin(_set_bit(0, 2, 1))
    '0b100'
    >>> bin(_set_bit(0b1000, 2, 1))
    '0b1100'
    >>> bin(_set_bit(0b1100, 2, 0))
    '0b1000'
    >>> bin(_set_bit(0b1101, 2, 0))
    '0b1001'
    """
    if v:
        return current | 1 << epaddr
    else:
        return current & ~(1 << epaddr)



class TestUsbDeviceCpuMemInterface(CommonUsbTestCase):

    maxDiff=None

    def setUp(self):
        self.iobuf = TestIoBuf()
        self.dut = UsbDeviceCpuMemInterface(self.iobuf, 3)

        self.packet_h2d = Signal(1)
        self.packet_d2h = Signal(1)
        self.packet_idle = Signal(1)


    def run_sim(self, stim):
        def padfront():
            yield
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

        run_simulation(self.dut, padfront(), vcd_name="vcd/%s.vcd" % self.id(), clocks={"usb_48": 4, "sys": 4})

    def _update_internal_signals(self):
        if False:
            yield

    ######################################################################
    ## Helpers
    ######################################################################

    def get_module(self, epaddr, name, obj=None):
        if obj is None:
            obj = self.dut
        epdir = EndpointType.epdir(epaddr)
        if epdir == EndpointType.OUT:
            module = getattr(obj, 'o{}'.format(name))
        elif epdir == EndpointType.IN:
            module = getattr(obj, 'i{}'.format(name))
        else:
            raise SystemError("Unknown endpoint type: %r" % epdir)
        return module

    def get_evsrc(self, epaddr):
        epnum = EndpointType.epnum(epaddr)
        return self.get_module(epaddr, "ep{}".format(epnum), obj=self.dut.packet)

    def get_ptr_csr(self, epaddr):
        epnum = EndpointType.epnum(epaddr)
        return self.get_module(epaddr, "ptr_ep{}".format(epnum))

    def get_len_csr(self, epaddr):
        epnum = EndpointType.epnum(epaddr)
        return self.get_module(epaddr, "len_ep{}".format(epnum))

    def set_csr(self, csr, epaddr, v):
        c = yield from csr.read()
        v = _set_bit(c, epaddr, v)
        yield from csr.write(v)

    # Data Toggle Bit
    def dtb(self, epaddr):
        v = yield from self.dut.dtb.read()
        return _get_bit(epaddr, v)

    def set_dtb(self, epaddr):
        yield from self.set_csr(self.dut.dtb, epaddr, 1)

    def clear_dtb(self, epaddr):
        yield from self.set_csr(self.dut.dtb, epaddr, 0)

    # Arm endpoint Bit
    def arm(self, epaddr):
        v = yield from self.dut.arm.read()
        return _get_bit(epaddr, v)

    def set_arm(self, epaddr):
        yield from self.set_csr(self.dut.arm, epaddr, 1)

    def clear_arm(self, epaddr):
        yield from self.set_csr(self.dut.arm, epaddr, 0)

    # Stall endpoint Bit
    def sta(self, epaddr):
        v = yield from self.dut.sta.read()
        return _get_bit(epaddr, v)

    def set_sta(self, epaddr):
        yield from self.set_csr(self.dut.sta, epaddr, 1)

    def clear_sta(self, epaddr):
        yield from self.set_csr(self.dut.sta, epaddr, 0)

    # IRQ / packet pending -----------------
    def trigger(self, epaddr):
        evsrc = self.get_evsrc(epaddr)
        v = yield evsrc.trigger
        return v

    def pending(self, epaddr):
        evsrc = self.get_evsrc(epaddr)
        v = yield evsrc.pending
        return v

    def clear_pending(self, epaddr):
        # Can't clear pending while trigger is active.
        while True:
            trigger = (yield from self.trigger(epaddr))
            if not trigger:
                break
            yield

        # Check the pending flag is raised
        self.assertTrue((yield from self.pending(epaddr)))

        # Clear pending flag
        mask = 1 << epaddr
        yield from self.dut.packet.pending.write(mask)
        yield
        # Check the pending flag has been cleared
        self.assertFalse((yield from self.trigger(epaddr)))
        self.assertFalse((yield from self.pending(epaddr)))

    # Endpoint state -----------------------
    def response(self, epaddr):
        if (yield from self.sta(epaddr)):
            return EndpointResponse.STALL

        pending = yield from self.pending(epaddr)
        armed = yield from self.arm(epaddr)
        if armed and not pending:
            return EndpointResponse.ACK

        return EndpointResponse.NAK

    def set_response(self, epaddr, v):
        assert isinstance(v, EndpointResponse), v
        if v == EndpointResponse.STALL:
            yield from self.set_sta(epaddr)
        else:
            yield from self.clear_sta(epaddr)

        if v == EndpointResponse.ACK:
            yield from self.set_arm(epaddr)
        elif v == EndpointResponse.NAK:
            yield from self.clear_arm(epaddr)

    # Get/set endpoint data ----------------
    def set_data(self, epaddr, data):
        """Set an endpoints buffer to given data to be sent."""
        assert isinstance(data, (list, tuple))
        self.ep_print(epaddr, "Set: %r", data)

        ep_ptr = yield from self.get_ptr_csr(epaddr).read()
        buf = self.get_module(epaddr, "buf")

        for i, v in enumerate(data):
            yield buf[ep_ptr+i].eq(v)

        ep_len = self.get_len_csr(epaddr)
        yield from ep_len.write(ep_ptr + len(data))

        yield

    def expect_data(self, epaddr, data):
        """Expect that an endpoints buffer has given contents."""
        ep_ptr = yield from self.get_ptr_csr(epaddr).read()
        buf = self.get_module(epaddr, "buf")

        # Make sure there is something pending
        self.assertTrue((yield from self.pending(epaddr)))

        actual_data = []
        for i in range(len(data), 0, -1):
            d = yield buf[ep_ptr-i]
            actual_data.append(d)

        self.ep_print(epaddr, "Got: %r (expected: %r)", actual_data, data)
        self.assertSequenceEqual(data, actual_data)


class TestUsbDeviceSimple(CommonUsbTestCase):

    maxDiff=None

    def setUp(self):
        self.iobuf = TestIoBuf()
        self.dut = UsbSimpleFifo(self.iobuf)

        self.states = [
            "WAIT",
            "RECV_DATA",
            "SEND_HAND",
            "SEND_DATA",
            "RECV_HAND",
        ]
        self.decoding = dict(enumerate(self.states))
        self.dut.state = Signal(max=len(self.states))
        self.dut.state._enumeration = self.decoding

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
                return "<Endpoint p:(%s,%s) %s d:%s>" % (int(self.trigger), int(self.pending), int(self.dtb), len(data))

        self.endpoints = {
            EndpointType.epaddr(0, EndpointType.OUT): Endpoint(),
            EndpointType.epaddr(0, EndpointType.IN):  Endpoint(),
            EndpointType.epaddr(1, EndpointType.OUT): Endpoint(),
            EndpointType.epaddr(1, EndpointType.IN):  Endpoint(),
            EndpointType.epaddr(2, EndpointType.OUT): Endpoint(),
            EndpointType.epaddr(2, EndpointType.IN):  Endpoint(),
        }

    def run_sim(self, stim):
        def padfront():
            yield from self.next_state("WAIT")
            yield
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
        run_simulation(self.dut, padfront(), vcd_name="vcd/%s.vcd" % self.id(), clocks={"usb_48": 4, "sys": 4})
        print("-"*10)

    def recv_packet(self):
        rx = (yield from self.dut.ev.pending.read()) & 0b1
        if not rx:
            return

        actual_data = []
        while range(0, 1024):
            yield from self.dut.obuf_head.write(0)
            empty = yield from self.dut.obuf_empty.read()
            if empty:
                break

            v = yield from self.dut.obuf_head.read()
            actual_data.append(v)
            yield

        yield from self.dut.ev.pending.write(0b1)
        yield

        #self.assertEqual(actual_data[0], 0b00000001)
        return actual_data

    def send_packet(self, pid, data=None):
        yield from self.dut.arm.write(0)
        armed = yield from self.dut.arm.read()
        self.assertFalse(armed)

        empty = yield from self.dut.obuf_empty.read()
        self.assertTrue(empty)

        #           sync,       pid
        pkt_data = [0b10000000, pid | ((0b1111 ^ pid) << 4)]
        if data is None:
            assert pid in (PID.ACK, PID.NAK, PID.STALL), (pid, data)
        else:
            assert pid in (PID.DATA0, PID.DATA1), pid
            pkt_data += data
            pkt_data += crc16(data)

        print("send_packet", pid, data)
        print("send_packet", pkt_data)
        for d in pkt_data:
            yield from self.dut.ibuf_head.write(d)
            yield
            yield
            yield
            yield

        empty = yield from self.dut.ibuf_empty.read()
        self.assertFalse(empty)

        yield from self.dut.arm.write(1)

    def next_state(self, state):
        self.assertIn(state, self.states)
        yield self.dut.state.eq(self.states.index(state))
        self.state = state

    def _update_internal_signals(self):
        def decode_pid(pkt_data):
            pkt_data = encode_data(pkt_data[:1])
            pidt = int(pkt_data[0:4][::-1], 2)
            pidb = int(pkt_data[4:8][::-1], 2)
            self.assertEqual(pidt ^ 0b1111, pidb)
            return PID(pidt)

        for ep in self.endpoints.values():
            if ep.trigger:
                ep.pending = True
                ep.trigger = False
        del ep

        if self.state == "WAIT":
            self.ep = None
            self.handshake = None

            pkt_data = yield from self.recv_packet()
            if not pkt_data:
                return

            self.assertEqual(len(pkt_data), 3, pkt_data)
            pid = decode_pid(pkt_data)
            pkt_data = encode_data(pkt_data)
            addr = int(pkt_data[8:8+7][::-1], 2)
            endp = int(pkt_data[8+7:8+7+4][::-1], 2)
            crc5 = int(pkt_data[8+7+4:][::-1], 2)

            print("WAIT      pid:", pid, "addr:", addr, "ep:", endp, "crc5:", crc5)
            self.assertEqual(crc5, crc5_token(addr, endp))

            if pid == PID.SETUP or pid == PID.OUT:
                self.ep = self.endpoints[EndpointType.epaddr(endp, EndpointType.OUT)]
                if pid == PID.SETUP:
                    self.handshake = EndpointResponse.ACK
                    self.ep.response = EndpointResponse.NAK
                    self.ep.dtb = False

                    iep = self.endpoints[EndpointType.epaddr(endp, EndpointType.IN)]
                    self.assertIsNot(self.ep, iep)
                    iep.response = EndpointResponse.NAK
                    iep.dtb = True
                    print(self.ep, iep)
                else:
                    self.handshake = self.ep.response
                yield from self.next_state("RECV_DATA")

            elif pid == PID.IN:
                self.ep = self.endpoints[EndpointType.epaddr(endp, EndpointType.IN)]
                self.handshake = self.ep.response

                if self.ep.response == EndpointResponse.ACK:
                    #self.assertIsNotNone(self.ep.data)
                    if self.ep.data is None:
                        self.ep.data = []
                    yield from self.next_state("SEND_DATA")
                else:
                    yield from self.next_state("SEND_HAND")
            else:
                assert False, pid

        elif self.state == "RECV_DATA":
            self.assertIsNotNone(self.ep)
            pkt_data = yield from self.recv_packet()
            if not pkt_data:
                return

            pid = decode_pid(pkt_data)
            print("RECV_DATA pid:", pid, "data:", pkt_data)

            if self.handshake == EndpointResponse.ACK:
                self.assertIsNone(self.ep.data)
                self.assertIn(encode_pid(pid), (encode_pid(PID.DATA0), encode_pid(PID.DATA1)))
                self.assertSequenceEqual(pkt_data[-2:], crc16(pkt_data[1:-2]))
                self.ep.data = pkt_data[1:-2]

            yield from self.next_state("SEND_HAND")

        elif self.state == "SEND_HAND":
            self.assertIsNotNone(self.ep)
            self.assertIsNotNone(self.handshake)
            pid = {
                EndpointResponse.STALL: PID.STALL,
                EndpointResponse.NAK:   PID.NAK,
                EndpointResponse.ACK:   PID.ACK,
            }[self.handshake]
            print("SEND_HAND pid:", pid)
            yield from self.send_packet(pid)
            if self.handshake == EndpointResponse.ACK:
                self.ep.trigger = True
                self.ep.dtb = not self.ep.dtb
            yield from self.next_state("WAIT")

        elif self.state == "SEND_DATA":
            self.assertIsNotNone(self.ep)
            self.assertIsNotNone(self.ep.data)
            pid = [PID.DATA0, PID.DATA1][self.ep.dtb]
            print("SEND_DATA pid:", pid, "data:", self.ep.data)
            yield from self.send_packet(pid, self.ep.data)
            self.ep.data = None
            yield from self.next_state("RECV_HAND")

        elif self.state == "RECV_HAND":
            self.assertIsNotNone(self.ep)
            pkt_data = yield from self.recv_packet()
            if not pkt_data:
                return

            pid = decode_pid(pkt_data)
            print("RECV_HAND pid:", pid)
            if pid != PID.ACK:
                raise SystemError(pkt_data)

            self.ep.trigger = True
            self.ep.dtb = not self.ep.dtb

            yield from self.next_state("WAIT")

    ######################################################################
    ## Helpers
    ######################################################################

    # IRQ / packet pending -----------------
    def trigger(self, epaddr):
        yield from self._update_internal_signals()
        return self.endpoints[epaddr].trigger

    def pending(self, epaddr):
        yield from self._update_internal_signals()
        return self.endpoints[epaddr].pending

    def clear_pending(self, epaddr):
        # Can't clear pending while trigger is active.
        for i in range(0, 100):
            trigger = (yield from self.trigger(epaddr))
            if not trigger:
                break
            yield
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
        assert isinstance(data, (list, tuple))
        if False:
            yield

        self.ep_print(epaddr, "Set: %r", data)
        self.endpoints[epaddr].data = data

    def expect_data(self, epaddr, data):
        """Expect that an endpoints buffer has given contents."""
        # Make sure there is something pending
        self.assertTrue((yield from self.pending(epaddr)))

        self.ep_print(epaddr, "expect_data: %s", data)
        actual_data = self.endpoints[epaddr].data
        assert actual_data is not None
        self.endpoints[epaddr].data = None

        self.ep_print(epaddr, "Got: %r (expected: %r)", actual_data, data)
        self.assertSequenceEqual(data, actual_data)

    def dtb(self, epaddr):
        if False:
            yield
        print("dtb", epaddr, self.endpoints[epaddr])
        return self.endpoints[epaddr].dtb


if __name__ == '__main__':
    import doctest
    import sys
    run_unittest = True
    if len(sys.argv) == 2 and sys.argv[1] == "doctest":
        sys.argv.pop(-1)
        sys.argv.append("-v")
        run_unittest = False
    doctest.testmod()
    if run_unittest:
        unittest.main()
