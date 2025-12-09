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
import re
import queue
from .transport import Transport, SerialTransport, TransportError

class ProtocolError(Exception):
    pass

class StahlError(Exception):
    pass

class StahlProtocol:
    """Formats commands, sends via Transport, parses responses."""
    RE_SET_VOL = re.compile(r"^CH(\d{2}) (\d\.\d{6})$")  # CHXX Y.YYYYYY
    RE_VOL = re.compile(r"^([+-]\d{2},\d{3}) V$")         # +/-yy,yyy V
    RE_TEMP = re.compile(r"^TEMP (\d{1,3}\.\d)ºC$")     # TEMP XXX.XºC
    RE_IDN = re.compile(r"^(.{5})\s(.{3})\s(.{1,2})\s(.{1})$") # DDDDD VVV C p
    RE_ERR = re.compile(r"^err$") # fixme

    def __init__(self, transport: Transport, write_timeout: float = 1.0, read_timeout: float = 1.0, ao_ranges:dict=None, device_serial:str=None):
        self.transport = transport
        self.write_timeout = write_timeout
        self.read_timeout = read_timeout
        self.ao_ranges = ao_ranges
        self.serial_number = device_serial

    def close(self):
        if self.transport:
            self.transport.close()
            self.transport = None

    def send_raw(self, cmdstr: str) -> None:
        data = (cmdstr + "\r").encode()
        self.transport.write(data)

    def read_raw(self) -> str:
        raw = self.transport.read_line(timeout=self.read_timeout)
        try:
            return raw.decode(errors="ignore").strip()
        except Exception as e:
            raise ProtocolError(f"Failed to decode raw response: {e}") from e

    # -------------- Commands --------------
    def lock_query(self) -> list[int]:
        try:
            cmdstr = f"{self.serial_number} LOCK"
            self.send_raw(cmdstr)
            raw = self.transport.read_line().rstrip()   # 4 bytes
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
        except (TransportError, ProtocolError) as e:
           raise e

    def info_query(self) -> dict:
        cmdstr = f"{self.serial_number} IDN"
        self.send_raw(cmdstr)
        resp = self.read_raw()
        idn_match = self.RE_IDN.match(resp)
        if not idn_match:
            raise ProtocolError(f"Query IDN failed. Response: {resp}")

        if len(resp.split()) != 4:
            raise ProtocolError(f"Invalid INFO response: {resp}")

        polarity_map = {
            'b': 'bipolar',
            'u': 'unipolar',
            'q': 'quadrupole',
            's': 'steerer',
        }

        pol = resp[3]
        if pol not in polarity_map:
            raise ProtocolError(f"Unknown polarity code '{pol}' in response: {resp}")

        return {
            'device_serial': resp[0],
            'range': resp[1],
            'ao_num': resp[2],
            'polarity': polarity_map[pol],
        }

    def set_voltage(self,ch:int, vol:float):
        """send: DDDDD CHXX Y.YYYYYY; receive: CHXX Y.YYYYYY"""
        ch_str = f"{ch:02d}"
        vol_str = f"{self._scale_to_norm(vol, ch):.6f}"
        cmd = f"{self.serial_number} CH{ch_str} {vol_str}"
        self.send_raw(cmd)
        resp = self.read_raw()
        set_vol = self.RE_SET_VOL.match(resp)
        if not set_vol:
            raise ProtocolError(f"Set voltage on channel {ch} failed. Response: {resp}")

    def mon_voltage(self, ch:int) -> float:
        """send: DDDDD QXX; receive: +/-yy,yyy"""
        ch_str = f"{ch:02d}"
        cmd = f"{self.serial_number} Q{ch_str}"
        self.send_raw(cmd)
        resp = self.read_raw()
        mon_vol = self.RE_VOL.match(resp)
        if not mon_vol:
            raise ProtocolError(f"Monitor voltage on channel {ch} failed. Response {resp}")
        mon_vol = mon_vol.group(1).replace(',', '.')
        mon_vol = float(mon_vol)
        return mon_vol

    def mon_temperature(self) -> float:
        """send: DDDDD TEMP; receive: TEMP XXX.XºC"""
        cmd = f"{self.serial_number} TEMP"
        self.send_raw(cmd)
        resp = self.read_raw()
        mon_temp = self.RE_TEMP.match(resp)
        if not mon_temp:
            raise ProtocolError(f"Monitor temperature failed.")
        mon_temp = float(mon_temp.group(1))
        return mon_temp

    # -------------- Helpers -----------------
    def _scale_to_norm(self, val:float|int, ch:int) -> float:
        """Convert an actual value (within -max_range to +max_range) to a normalized value (0 to 1)"""
        ao_range = self.ao_ranges[ch]
        return (val + ao_range) / (2 * ao_range)

    def _scale_to_range(self, val:float, ch:int):
        """Convert a normalized value (0 to 1) to the specified range (-max_range to +max_range)"""
        ao_range = self.ao_ranges[ch]
        return 2 * ao_range * val - ao_range

class StahlDevice:
    """High-level device API. Channels indexed 0..N-1."""
    def __init__(self, port=None, baud_rate=9600, vid=None, pid=None, serial_number=None, ao_ranges=None):
        transport = SerialTransport(port=port, baud=baud_rate, vid=vid, pid=pid, serial_number=serial_number)
        serial_number = transport.serial_number
        self.protocol = StahlProtocol(transport=transport, ao_ranges=ao_ranges, device_serial=serial_number)

    def close(self):
        self.protocol.close()

    def get_device_info(self) -> dict:
        return self.protocol.info_query()

    def set_voltage(self, channel: int, voltage: float):
        self.protocol.set_voltage(channel, voltage)

    def monitor_voltage(self, channel: int) -> float:
        return self.protocol.mon_voltage(channel)

    def get_status(self, channel:int=None) -> list[int]|int:
        """Get the lock status of all channels, if no specific channel is specified."""
        lock_status = self.protocol.lock_query()
        if channel is not None:
            return lock_status[channel]
        return lock_status

    def monitor_temperature(self) -> float:
        return self.protocol.mon_temperature()


class HV_Worker(Worker):
    def init(self):
        """Initialises communication with the device. When BLACS (re)starts"""
        self.stahl = StahlDevice(port=self.port, baud_rate=self.baud_rate,
                                 vid=self.vid, pid=self.pid, serial_number=self.serial_number,
                                 ao_ranges=self.ao_ranges)

        # setting values in separate thread
        self.job_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._setting_loop, daemon=True)
        self.worker_thread.start()

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
            results[ch_name] = self.stahl.monitor_voltage(i)
        return results

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.h5file = h5_file
        self.device_name = device_name

        with h5py.File(h5_file, 'r') as hdf5_file:
            group = hdf5_file['devices'][device_name]
            ao_data = group['AO'][:]

        # prepare events
        events = []
        for row in ao_data:
            t = row['time']
            voltages = {int(ch[3:]): row[ch] for ch in row.dtype.names if ch != 'time'}
            events.append((t, voltages))

        for event in events:
            self.job_queue.put(event)

        start_time = time.perf_counter() # fixme: when should we start sending commands? buffered! waits?
        self.start_time = start_time

        # self.job_queue.join() # todo: block transition_to_buffered?

        final_values = {ch: ao_data[-1][ch] for ch in ao_data[-1].dtype.names if ch != 'time'}
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
        """ Assumption: only one value per channel """
        print(f"[{t}]")
        for channel, voltage in voltages.items():
            self.stahl.set_voltage(channel, voltage)
            elapsed = time.perf_counter() - (start_time or 0)
            print(f"[{elapsed:.3f}s] CH{channel} = {voltage}")

            # if self.stahl.get_status(channel) == 1:
            #     rich_print(f"[{t:.3f}s] CH{channel} = {voltage} is overloaded.", color="orange")
            # else:
            #     elapsed = time.perf_counter() - (start_time or 0)
            #     print(f"[{elapsed:.3f}s] CH{channel} = {voltage}")

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def transition_to_manual(self):
        return True

    def reprogram(self, kwargs):
        print("Reprogramming device with:")

        for conn, voltage in self.front_panel_values.items():
            print(f"{conn}: {voltage:.3f} V")
            num = int(conn[3:]) # reduce "ch "
            self.stahl.set_voltage(num, voltage)

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._append_front_panel_values_to_manual(self.front_panel_values, current_time)

    def monitor_voltage(self, kwargs):
        dict = self.check_remote_values()
        rich_print("Remote Values: ", color=YELLOW)
        for k, v in dict.items():
            print(f"\t{k}: {v}")

    def monitor_temperature(self):
        temp = self.stahl.monitor_temperature()
        if temp > 55.0:
            rich_print("Temperature %d °C > 55°C indicates a possible ventilation problem or other malfunction. The device should be switched off." % temp, color=RED)
        else:
            print("TEMPERATURE: ", temp)

    def check_lock_status(self):
        locks = self.stahl.get_status()
        for idx, lock in enumerate(locks):
            if lock == 1:
                vol = self.stahl.monitor_voltage(channel=idx)
                rich_print(f"Ch{idx} is overloaded -- {vol} V.", color=RED)

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