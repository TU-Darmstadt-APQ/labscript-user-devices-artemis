import queue

from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import h5py
import threading
from zprocess import rich_print
from user_devices.logger_config import logger
import time
from datetime import datetime
from .caen_protocol import CAENDevice
import numpy as np

STATUS_BITS_tech = {
    0: "ON",
    1: "Ramp UP",
    2: "Ramp DOWN",
    3: "OVC: IMON >= ISET", # overcurrent
    4: "OVV: VMON > VSET + (2% of VSET) + 2V", # overvoltage
    5: "ONV: VMON < VSET - (2% of VSET) - 2V", # undervoltage
    6: "TRIP: Ch OFF via TRIP (Imon >= Iset during TRIP)",
    7: "OVP : Output Power > Max",
    8: "TWN: Temperature Warning",
    9: "OVT: TEMP > 65°C",
    10: "KILL: CH in KILL via front panel and back panel",
    11: "INTLK: CH in INTERLOCK via front panel and back panel",
    12: "ISDIS: CH is disabled",
    13: "FAIL: Generic fail",
    14: "LOCK: Ch control switch on ON/EN and one of these conditions is TRUE:",
    15: "MAXV: VMON > HVMAX set via trimmer",
}

STATUS_BITS = {
    0: "Channel is on",
    1: "Channel is ramping up",
    2: "Channel is ramping down",
    3: "Channel is in overcurrent",
    4: "Channel is in overvoltage",
    5: "Channel is in undervoltage",
    6: "TRIP: Ch OFF via TRIP (Imon >= Iset during TRIP)", # trip= max time overcurrent allowed to last
    7: "Channel is in max V",
    8: "Temperature Warning",
    9: "Temperature over 65°C",
    10: "Channel is in kill",
    11: "Channel is in interlock",
    12: "Channel is disabled",
    13: "Channel is failed",
    14: "Channel control switch on ON/EN",
    15: "Channel is in overvoltage HVMAX set via trimmer",
}

class CAENWorker(Worker):
    def init(self):
        """Initializes connection to CAEN device (direct Serial or USB or Ethernet)"""
        self.caen = CAENDevice(port=self.port, baud_rate=self.baud_rate, pid=self.pid, vid=self.vid, serial_number=self.serial_number)

        for ch in range(8):
            self.caen.enable_channel(ch, True)

        print("#################### CH STATUS #####################")
        for ch in range(8):
            status = self.caen.get_status(channel=ch)
            status_dec_str = self._decode_status(ch, int(status))
            print(status_dec_str)
        print("#####################################################")

        print("Control mode : ", self.caen.monitor_control_mode())
        print("Board serial number : ", self.caen.read_board_serial())

        # setting values in separate thread
        self.job_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._setting_loop, daemon=True)
        self.worker_thread.start()

    def shutdown(self):
        """Closes connection."""
        self.job_queue.put(None) # put sentinel unblock queue.get()
        self.worker_thread.join()
        self.caen.close()


    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs at the end of the shot."""
        rich_print(f"---------- Manual MODE start: ----------", color=BLUE)
        self.front_panel_values = front_panel_values
        return front_panel_values

    def check_remote_values(self):
        results = {}
        for i in range(8):
            ch_name = f'CH {i}'
            actual = self.caen.monitor_voltage(i)
            results[ch_name] = actual
        return results

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh): 
        """transitions the device to buffered shot mode, 
        reading the shot h5 file and taking the saved instructions from 
        labscript_device.generate_code and sending the appropriate commands 
        to the hardware. 
        Runs at the start of each shot."""
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.restored_from_final_values = False  # Drop flag
        self.h5file = h5_file  # Store path to h5 to write back from front panel
        self.device_name = device_name

        # Prepare events
        with h5py.File(h5_file, 'r') as hdf5_file:
            group = hdf5_file['devices'][device_name]
            AO_data = group['AO_buffered'][:]

        # Prepare events
        events = []
        for row in AO_data:
            t = row['time']
            voltages = {self._get_channel_num(ch): row[ch] for ch in row.dtype.names if ch != 'time'}
            events.append((t, voltages))

        # NOTE: The last event is added only to ensure a non-zero experiment duration.
        # If it duplicates the previous event, it is safe to drop it.
        if events[-1][1] == events[-2][1]:
            events = events[:-1]

        for event in events:
            self.job_queue.put(event)

        self.job_queue.join() # blocks until all task are done

        # return last values to update GUI
        final_values = events[-1][1]
        return final_values

    def _setting_loop(self):
        while True:
            item = self.job_queue.get()
            if item is None:
                self.job_queue.task_done()
                break

            t, voltages = item
            try:
                self._apply_event(t, voltages)
                self._block_until_set(voltages)

            except Exception as e:
                logger.error("Error by setting voltages to CAEN", e)
            finally:
                self.job_queue.task_done()

    def _apply_event(self, t, voltages):
        """ Assumption: only one value per channel """
        for channel, voltage in voltages.items():
            self.caen.set_voltage(channel, voltage)
            if not self._check_channel_state(channel): # channel is not settable
                rich_print(f" CH{channel} = {voltage} is OFF or/and disabled.", color=ORANGE)
            else:
                print(f"[{t:.3f}s] CH{channel} = {voltage}")

    def _block_until_set(self, voltages):
        delta = 1.0
        settled = set()

        while len(settled) < len(voltages):
            for ch, target in voltages.items():
                mon = self.caen.monitor_voltage(ch)
                if ch not in settled and abs(mon - target) < delta:
                    settled.add(ch)

        rich_print(" ---- All channels settled ---- ", color=GREEN)


    def _get_channel_num(self, channel: str) -> int:
        ch_lower = channel.lower()
        if ch_lower.startswith("ao "):
            channel_num = int(ch_lower[3:])  # 'ao 3' -> 3
        elif ch_lower.startswith("ao"):
            channel_num = int(ch_lower[2:])  # 'ao3' -> 3
        elif ch_lower.startswith("channel"):
            _, channel_num_str = channel.split()  # 'channel 1' -> 1
            channel_num = int(channel_num_str)
        elif ch_lower.startswith("ch "):
            channel_num = int(ch_lower[3:].strip())  # 'ch 0', 'ch 3', 'ch 7' -> 0, 3, 7
        elif ch_lower.startswith("ch"):
            channel_num = int(ch_lower[2:].strip())  # 'ch0', 'ch03', 'ch7' -> 0, 3, 7
        else:
            raise ValueError(f"Unexpected channel name format: '{channel}'")

        return channel_num

    def _decode_status(self, ch:int, st:int) -> str:
        status = f"Channel {ch}: "
        # print(f"[DEBUG]: {type(bits16)}  = {repr(bits16)}, {bits16}")

        for bit, meaning in STATUS_BITS.items():
            state = bool(st & (1 << bit))
            if bit == 0 and state:
                status += "ON"
            elif bit == 0 and not state:
                status += "OFF"
            elif state:
                status += "\n\t" + meaning
            else:
                continue
        return status

    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. 
        Runs at the end of the shot."""
        rich_print(f"---------- Begin transition to Manual: ----------", color=BLUE)
        return True

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

    def reprogram_CAEN(self, kwargs):
        for channel, voltage in self.front_panel_values.items():
            ch_num = self._get_channel_num(channel)
            self.caen.set_voltage(ch_num, voltage)
            # store the values from manual to hdf5 file.
            if not self._check_channel_state(ch_num):  # channel is not settable
                rich_print(f" CH{ch_num} = {voltage} is OFF or/and disabled.", color=ORANGE)
            else:
                print(f"→ {channel}: {voltage:.2f} V")
            logger.info(f"[CAEN] Setting {channel} to {voltage:.2f} V (manual mode)")
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._append_front_panel_values_to_manual(self.front_panel_values, current_time)

    def monitor_CAEN(self, kwargs):
        """ Monitor voltages on channels, display in terminal """
        rich_print("Channels monitor voltage values", color=BLUE)
        for channel, voltage in self.front_panel_values.items():
            ch_num = self._get_channel_num(channel)
            mon_voltage = self.caen.monitor_voltage(ch_num)
            print(f"→ {channel}: Monitor: {mon_voltage:.2f} \t GUI: {voltage:.2f} V")
            logger.info(f"[CAEN] Monitoring {channel} with {mon_voltage:.2f} V (manual mode)")

    def check_status(self, kwargs):
        rich_print("Channels status", color=BLUE)
        for channel in self.front_panel_values.keys():
            ch_num = self._get_channel_num(channel)
            status_str = self._decode_status(ch=ch_num, st=int(self.caen.get_status(ch_num)))
            print(status_str)


    def _append_front_panel_values_to_manual(self, front_panel_values, current_time):
        """
            Append front-panel voltage values to the 'AO_manual' dataset in the HDF5 file.

            This method records the current manual voltage settings (from the front panel)
            along with a timestamp into the 'AO_manual' table inside the device's HDF5 group.
            It assumes that `self.h5file` and `self.device_name` have been set
            (in `transition_to_buffered`). If not, a RuntimeError is raised.

            Args:
            front_panel_values (dict):
                Dictionary mapping channel names (e.g., 'CH01') to voltage values (float).
            current_time (str):
                The timestamp (formatted as a string) when the values were recorded

            Raises:
                RuntimeError: If `self.h5file` is not set (i.e., manual values are being saved before
                the system is in buffered mode).
            """
        # Check if h5file is set (transition_to_buffered must be called first)
        if not hasattr(self, 'h5file') or self.h5file is None:
            raise RuntimeError(
                "Cannot save manual front-panel values: "
                "`self.h5file` is not set. Make sure `transition_to_buffered()` has been called before sending to the device."
            )

        with h5py.File(self.h5file, 'r+') as hdf5_file:
            group = hdf5_file['devices'][self.device_name]
            dset = group['AO_manual']
            old_shape = dset.shape[0]
            dtype = dset.dtype
            connections = [name for name in dset.dtype.names if name != 'time']  # 'CH 1'

            # Create new data row
            new_row = np.zeros((1,), dtype=dtype)
            new_row['time'] = current_time
            for conn in connections:
                channel_name = conn  # 'CH 1'
                new_row[conn] = front_panel_values.get(channel_name, 0.0)

            # Add new row to table
            dset.resize(old_shape + 1, axis=0)
            dset[old_shape] = new_row[0]

    def _check_channel_state(self, ch:int) -> bool:
        settable = False
        status = int(self.caen.get_status(ch))

        bit0_on = bool(status & (1 << 0))  # 1 = ON, 0 = OFF
        bit12_disabled = bool(status & (1 << 12))

        if bit0_on and not bit12_disabled: # ON and not disabled
            settable = True

        return settable
# --------------------contants
BLUE = '#66D9EF'
GREEN = '#008000'
ORANGE = '#FFA500'