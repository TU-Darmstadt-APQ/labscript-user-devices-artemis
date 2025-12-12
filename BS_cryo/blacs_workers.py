from blacs.tab_base_classes import Worker
from labscript import LabscriptError
from user_devices.logger_config import logger
from datetime import datetime
import h5py
import numpy as np
from zprocess import rich_print
from labscript_utils import properties
import threading
import time
from datetime import datetime as dt
from typing import Optional, Union, Tuple, List
import serial
import re
import serial.tools.list_ports
import queue
from user_devices.Stahl_HV.transport import Transport, SerialTransport, TransportError
from dataclasses import dataclass

@dataclass
class IDNInfo:
    serial: str
    range_str: str
    ao_num: str
    polarity_code: str

@dataclass
class Ack:
    pass

@dataclass
class ErrorResponse:
    code:int

class ProtocolError(Exception):
    pass

class StahlError(Exception):
    def __init__(self, code:int):
        error_map = {
            1: "Command not recognized",
            2: "Channel number out of range",
            3: "Scaled voltage bigger than 1.0000"
        }
        message = error_map[code]
        rich_print(f"[Device ERROR] {message} (code={code})", color=RED)

class StahlProtocol:
    """Formats commands, sends via Transport, parses responses."""
    RE_SET_VOL = re.compile(r"^CH(\d{2}) (\d\.\d{6})$")  # CHXX Y.YYYYYY
    RE_VOL_CURR = re.compile(r'^([+-]?\d+(?:[.,]\d+)?) V ([+-]?\d+(?:[.,]\d+)?) mA$')       # +/-y V +/- z mA
    RE_VOL = re.compile(r"^([+-]?\d+(?:[.,]\d+)?) V$")
    RE_CURR = re.compile(r"^([+-]?\d+(?:[.,]\d+)?) mA$")
    RE_TEMP = re.compile(r"^TEMP (\d{1,3}(?:[.,]\d+)?)C (\d{1,3}(?:[.,]\d+)?)C$") # TEMP xC yC
    RE_IDN = re.compile(r"^(.{5})\s(.+)\s(.+)\s(.{1})$") # DDDDD VVV C p
    RE_ERROR = re.compile(r"^ERROR0(\d{1,2})$")
    RE_ACK = re.compile(r"^\x06\r?$")


    def __init__(self, transport: Transport, write_timeout: float = 1.0, read_timeout: float = 1.0):
        self.transport = transport
        self.write_timeout = write_timeout
        self.read_timeout = read_timeout

    def close(self):
        if self.transport:
            self.transport.close()
            self.transport = None

    def normalize_number(self, s:str) -> float:
        return float(s.replace(',', '.'))

    def parse(self, raw: Union[bytes, str]) -> Union[float, Tuple, Ack, ErrorResponse, IDNInfo, None]:
        if isinstance(raw, bytes):
            s = raw.decode().strip()
        else:
            s = raw.strip()

        if s == "":
            return None

        if self.RE_ACK.match(s):
            return Ack()

        m = self.RE_ERROR.match(s)
        if m:
            code = int(m.group(1))
            return ErrorResponse(code=code)

        m = self.RE_SET_VOL.match(s)
        if m:
            return "SET_ECHO", m.group(1), m.group(2)

        m = self.RE_VOL_CURR.match(s)
        if m:
            v = self.normalize_number(m.group(1))
            i = self.normalize_number(m.group(2))
            return v, i

        m = self.RE_VOL.match(s)
        if m:
            v = self.normalize_number(m.group(1))
            return v

        m = self.RE_CURR.match(s)
        if m:
            i = self.normalize_number(m.group(1))
            return i

        m = self.RE_TEMP.match(s)
        if m:
            t1 = self.normalize_number(m.group(1))
            t2 = self.normalize_number(m.group(2))
            return t1, t2

        m = self.RE_IDN.match(s)
        if m:
            return IDNInfo(
                serial=m.group(1),
                range_str=m.group(2),
                ao_num=m.group(3),
                polarity_code=m.group(4)
            )

        raise ProtocolError(f"Unrecognized response: {s!r}")

    def _send_raw(self, cmdstr: str) -> None:
        data = (cmdstr + "\r").encode()
        self.transport.write(data)

    def _read_raw(self) -> bytes:
        raw = self.transport.read_line(timeout=self.read_timeout)
        return raw

    def exchange(self, cmd:str, expect_ack:bool=False):
        self._send_raw(cmd)
        raw = self._read_raw()
        parsed = self.parse(raw)
        return parsed

    # -------------- Commands --------------

    def info_query(self) -> IDNInfo:
        cmd = "IDN"
        resp = self.exchange(cmd)
        if not isinstance(resp, IDNInfo):
            raise ProtocolError(f"Invalid IDN response : {resp}")

        return resp

    def set_voltage(self, serial_number:str, ch:int, value:float) -> None:
        ch_str = f"{ch:02d}"
        vol_str = f"{value:.6f}"

        cmd = f"{serial_number} CH{ch_str} {vol_str}"
        resp = self.exchange(cmd)

        if isinstance(resp, Ack):
            return
        if isinstance(resp, tuple) and resp[0] == "SET_ECHO":
            return
        if isinstance(resp, ErrorResponse):
            error_map = {
                1: "Command not recognized",
                2: "Channel number {} out of range",
                3: "Value to set on ch={} out of range"
            }
            template = error_map.get(resp.code, "Unknown error code {}")
            message = template.format(ch if resp.code == 2 or resp.code == 1  else resp.code)
            rich_print(f"[Device WARNING] {message}  (code={resp.code})", color=RED)
            return

        raise ProtocolError(f"Unexpected set_voltage response : {resp}")

    def mon_voltage_current(self,serial_number:str, ch:int):
        ch_str = f"{ch:02d}"
        cmd = f"{serial_number} Q{ch_str}"
        resp = self.exchange(cmd)

        if isinstance(resp, tuple) and isinstance(resp[0], float) and isinstance(resp[1], float):
            return resp
        raise ProtocolError(f"Invalid Volt+Curr response : {resp}")

    def mon_voltage(self, serial_number: str, ch: int):
        ch_str = f"{ch:02d}"
        cmd = f"{serial_number} U{ch_str}"
        resp = self.exchange(cmd)

        if isinstance(resp, float):
            return resp
        raise ProtocolError(f"Invalid voltage response : {resp}")

    def mon_current(self, serial_number: str, ch: int):
        ch_str = f"{ch:02d}"
        cmd = f"{serial_number} I{ch_str}"
        resp = self.exchange(cmd)

        if isinstance(resp, float):
            return resp
        raise ProtocolError(f"Invalid current response : {resp}")

    def mon_temperature(self, serial_number:str):
        cmd = f"{serial_number} TEMP"
        resp = self.exchange(cmd)
        if isinstance(resp, tuple) and isinstance(resp[0], float) and isinstance(resp[1], float):
            return resp
        raise ProtocolError(f"Invalid temperature response : {resp}")

    def lock_query(self, serial_number:str):
        cmd = f"{serial_number} LOCK"
        self._send_raw(cmd)
        raw = self._read_raw().rstrip()
        if not raw and len(raw)<4:
            raise ProtocolError(f"Invalid LOCK response length : {len(raw) if raw else 0}")
        b3, b2, b1, b0 = raw
        n3 = b3 & 0x0F
        n2 = b2 & 0x0F
        n1 = b1 & 0x0F
        n0 = b0 & 0x0F

        channels = [
            (n0 >> 0) & 1,  # ch1
            (n0 >> 1) & 1,  # ch2
            (n0 >> 2) & 1,  # ch3
            (n0 >> 3) & 1,  # ch4

            (n1 >> 0) & 1,  # ch5
            (n1 >> 1) & 1,  # ch6
            (n1 >> 2) & 1,  # ch7
            (n1 >> 3) & 1,  # ch8

            (n2 >> 0) & 1,  # ch9
            (n2 >> 1) & 1,  # ch10
            (n2 >> 2) & 1,  # ch11
            (n2 >> 3) & 1,  # ch12

            (n3 >> 0) & 1,  # ch13
            (n3 >> 1) & 1,  # ch14
            (n3 >> 2) & 1,  # ch15
            (n3 >> 3) & 1,  # ch16
        ]

        return channels


class StahlDevice:
    def __init__(self, protocol:StahlProtocol, serial_number:str, ao_ranges):
        self.protocol = protocol
        self.serial_number = serial_number
        self.ao_ranges = ao_ranges

    def get_info(self) -> IDNInfo:
        return self.protocol.info_query()

    def set_voltage(self, ch:int, voltage:float):
        norm = self._scale_to_norm(voltage, ch)
        self.protocol.set_voltage(self.serial_number, ch=ch, value=norm)

    def get_voltage(self, ch) -> float:
        return self.protocol.mon_voltage(self.serial_number, ch=ch)

    def get_current(self, ch) -> float:
        return self.protocol.mon_current(self.serial_number, ch=ch)

    def get_voltage_and_current(self, ch:int) -> Tuple:
        return self.protocol.mon_voltage_current(self.serial_number, ch=ch)

    def get_temperature(self) -> Tuple:
        return self.protocol.mon_temperature(self.serial_number)

    def get_lock_status(self) -> List[int]:
        return self.protocol.lock_query(self.serial_number)

    # -------------- Helpers: Scaling -----------------
    def _scale_to_norm(self, val:float|int, ch:int) -> float:
        """Convert an actual value (within -max_range to +max_range) to a normalized value (0 to 1)"""
        ao_range = self.ao_ranges[ch]
        return (val + ao_range) / (2 * ao_range)

    def _scale_to_range(self, val:float, ch:int):
        """Convert a normalized value (0 to 1) to the specified range (-max_range to +max_range)"""
        ao_range = self.ao_ranges[ch]
        return 2 * ao_range * val - ao_range

    def close(self):
        if self.protocol is not None:
            self.protocol.close()
            self.protocol=None


class BS_Worker(Worker):
    def init(self):
        """Initialises communication with the device. When BLACS (re)starts"""
        transport = SerialTransport(baud=self.baud_rate, port=self.port, vid=self.vid, pid=self.pid, serial_number=self.serial_number)
        serial_number = transport.serial_number
        print("Retrieved serial number: %s \t Given serial number: %s" % (serial_number, self.serial_number))
        self.serial_number = serial_number
        protocol = StahlProtocol(transport=transport)
        self.stahl = StahlDevice(protocol=protocol, ao_ranges=self.ao_ranges, serial_number=self.serial_number)

        # setting values in separate thread
        self.job_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._setting_loop, daemon=True)
        self.worker_thread.start()

        # print("TEST ALL IMPLEMENTED COMMANDS")
        # print("INFO: \t", self.stahl.get_info())
        # print("get_vol: \t", self.stahl.get_voltage(ch=9))
        # print("get_temp: \t", self.stahl.get_temperature())
        # print("get_cuur: \t", self.stahl.get_current(ch=9))
        # print("set_vol: \t", self.stahl.set_voltage(ch=9, voltage=3.21144))
        # print("lock: \t", self.stahl.get_lock_status())
        # print("get_both: \t", self.stahl.get_voltage_and_current(ch=9))
        # print("END TEST")

    def shutdown(self):
        self.stahl.close()

    def program_manual(self, front_panel_values):
        """Allows for user control of the device via the BLACS_tab,
        setting outputs to the values set in the BLACS_tab widgets.
        Runs before and after shot."""
        rich_print(f"---------- Manual MODE start: ----------", color=BLUE)
        self.front_panel_values = front_panel_values
        return front_panel_values

    def check_remote_values(self):
        results = {}
        for i in range(self.num_ao):
            ch_name = 'ch %d' % i
            results[ch_name] = self.stahl.get_voltage(i)
        return results

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.h5file = h5_file
        self.device_name = device_name

        with h5py.File(h5_file, 'r') as hdf5_file:
            group = hdf5_file['devices'][device_name]
            ao_data = group['AO_buffered'][:]

        # prepare events
        events = []
        for row in ao_data:
            t = row['time']
            voltages = {int(ch[3:]): row[ch] for ch in row.dtype.names if ch != 'time'}
            events.append((t, voltages))
            if self.pre_programmed: # store only first values
                break

        for event in events:
            self.job_queue.put(event)

        start_time = time.perf_counter()  # fixme: how to start commands sequence as soon as it enters buffered mode?
        self.start_time = start_time

        if self.pre_programmed:
            self.job_queue.join() # blocks transition_to_buffered

        last_voltages = events[-1][1]
        final_values = {"ch %d" % ch: val for ch, val in last_voltages.items()}
        rich_print(f"---------- End transition to Buffered: ----------", color=BLUE)
        return final_values

    def _setting_loop(self):
        while True:
            item = self.job_queue.get()
            if item is None:
                self.job_queue.task_done()
                break

            event_time, voltages = item
            now = time.perf_counter()
            delay = event_time - (now - self.start_time)
            if delay > 0:
                time.sleep(delay)

            try:
                self._apply_event(event_time, voltages, self.start_time)

            except Exception as e:
                logger.error("Error by setting voltages to CAEN", e)
            finally:
                self.job_queue.task_done()

    def _apply_event(self, t, voltages, start_time):
        print(f"[{t}]")
        for channel, voltage in voltages.items():
            self.stahl.set_voltage(channel, voltage)
            elapsed = time.perf_counter() - (start_time or 0)
            print(f"[{elapsed:.3f}s] CH{channel} = {voltage:.6f}")

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def transition_to_manual(self):
        rich_print(f"---------- Start transition to Manual: ----------", color=BLUE)

        return True

    def reprogram(self, kwargs):
        print("Reprogramming device with:")

        for conn, voltage in self.front_panel_values.items():
            print(f"{conn}: {voltage:.3f} V")
            num = int(conn[3:])  # reduce "ch "
            self.stahl.set_voltage(num, voltage)

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._append_front_panel_values_to_manual(self.front_panel_values, current_time)

    def monitor_voltage(self, kwargs):
        ch_vol_dict = self.check_remote_values()
        rich_print("Remote Values: ", color=YELLOW)
        for k, v in ch_vol_dict.items():
            print(f"\t{k}: {v}")

    def monitor_temperature(self):
        t1, t2 = self.stahl.get_temperature()
        if t1 > 55.0 or t2 > 55.0:
            rich_print(
                "Temperature (%.1f, %.1f) °C > 55°C indicates a possible ventilation problem or other malfunction. "
                "The device should be switched off." %(t1, t2),
                color=RED)
        else:
            print("TEMPERATURE: ", t1, t2)

    def check_lock_status(self):
        all_good = True
        locks = self.stahl.get_lock_status()
        for idx, lock in enumerate(locks):
            if lock == 1:
                all_good = False
                vol = self.stahl.get_voltage(ch=idx)
                rich_print(f"Ch{idx} is overloaded -- {vol} V.", color=RED)
        if all_good:
            print("Status OK")

    def _append_front_panel_values_to_manual(self, front_panel_values, current_time):
        """ Append front-panel voltage values to the 'AO_manual' dataset in the HDF5 file. """
        # Check if h5file is set (transition_to_buffered must be called first)
        if not hasattr(self, 'h5file') or self.h5file is None:
            raise Exception('HDF5 file not initialized. Run the experiment shot first.')

        with h5py.File(self.h5file, 'r+') as hdf5_file:
            group = hdf5_file['devices'][self.device_name]

            dset = group['AO_manual']
            old_shape = dset.shape[0]
            dtype = dset.dtype
            connections = [name for name in dset.dtype.names if name != 'time']

            # Create new data row
            new_row = np.zeros((1,), dtype=dtype)
            new_row['time'] = current_time
            for conn in connections:
                new_row[conn] = front_panel_values.get(conn, 0.0)

            # Add new row to table
            dset.resize(old_shape + 1, axis=0)
            dset[old_shape] = new_row[0]

# --------------------contants
BLUE = '#66D9EF'
YELLOW = '#F5E727'
RED = '#F52727'
GREEN = '#3FDB3D'
