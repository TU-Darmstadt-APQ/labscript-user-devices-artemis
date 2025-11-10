from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import h5py
import threading
from zprocess import rich_print
from user_devices.logger_config import logger
import time
from datetime import datetime
from .caen_protocol import Caen
import numpy as np

class CAENWorker(Worker):
    def init(self):
        """Initializes connection to CAEN device (direct Serial or USB or Ethernet)"""
        self.final_values = {}
        self.caen = Caen(self.port, self.baud_rate, vid=self.vid, pid=self.pid, verbose=True, serial_number=self.serial_number)

        # for running the buffered experiment in a separate thread:
        self.thread = None
        self._stop_event = threading.Event()
        self._finished_event = threading.Event()
        
    def shutdown(self):
        """Closes connection."""
        self._stop_event.set()
        self.thread.join()
        self.caen.close_connection()

    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs at the end of the shot."""
        rich_print(f"---------- Manual MODE start: ----------", color=BLUE)
        print(f"front panel values: {front_panel_values}")

        self.front_panel_values = front_panel_values

        if not getattr(self, 'restored_from_final_values', False):
            print("Front panel values (before shot):")
            for ch_name, voltage in front_panel_values.items():
                print(f"  {ch_name}: {voltage:.2f} V")

            # Restore final values from previous shot, if available
            if self.final_values:
                for ch_num, value in self.final_values.items():
                    front_panel_values[f'CH {int(ch_num)}'] = value

            print("\nFront panel values (after shot):")
            for ch_num, voltage in self.final_values.items():
                print(f"  {ch_num}: {voltage:.2f} V")

            self.final_values = {}  # Empty after restoring
            self.restored_from_final_values = True

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
        self.final_values = {}  # Store the final values to update GUI during transition_to_manual
        self.h5file = h5_file  # Store path to h5 to write back from front panel
        self.device_name = device_name

        with h5py.File(h5_file, 'r') as hdf5_file:
            group = hdf5_file['devices'][device_name]
            AO_data = group['AO_buffered'][:]

        # Prepare events
        events = []
        for row in AO_data:
            t = row['time']
            voltages = {ch: row[ch] for ch in row.dtype.names if ch != 'time'}
            events.append((t, voltages))

        # Create and launch thread
        self._stop_event.clear()
        self._finished_event.clear()
        self.thread = threading.Thread(target=self._run_experiment_sequence, args=(events,))
        self.thread.start()

        return
        
    def _run_experiment_sequence(self, events):
        try:
            start_time = time.time()
            for t, voltages in events:
                now = time.time()
                wait_time = t - (now - start_time)
                if wait_time > 0:
                    time.sleep(wait_time)
                print(f"[Time: {datetime.now()}] \n")
                for conn_name, voltage in voltages.items():
                    channel_num = self._get_channel_num(conn_name)
                    self.caen.set_voltage(channel_num, voltage)
                    self.final_values[channel_num] = voltage
                    print(f"[{t:.3f}s] --> Set {conn_name} (#{channel_num}) = {voltage}")
                    if self._stop_event.is_set():
                        return
        finally:
            self._finished_event.set()
            print(f"[Thread] finished all events !")

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

    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. 
        Runs at the end of the shot."""
        self._finished_event.wait()
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
# --------------------contants
BLUE = '#66D9EF'