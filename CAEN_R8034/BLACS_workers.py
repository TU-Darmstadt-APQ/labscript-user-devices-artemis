from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import h5py
import threading
from zprocess import rich_print
from user_devices.logger_config import logger
import time
from datetime import datetime
from .caen_protocol import Caen


class CAENWorker(Worker):
    def init(self):
        """Initializes connection to CAEN device (direct Serial or USB or Ethernet)"""
        self.final_values = {}
        self.caen = Caen(self.port, self.baud_rate, self.pid, self.vid)

        # set remote control
        self.caen.set_control_mode('REMOTE')

        # for running the buffered experiment in a separate thread:
        self.thread = None
        self._stop_event = threading.Event()
        self._finished_event = threading.Event()
        
    def shutdown(self):
        """Closes connection."""
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

        rich_print(f"---------- END transition to Buffered: ----------", color=BLUE)
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

        self.thread.join()
        if not self._finished_event.is_set():
            print("WARNING: experiment sequence did not finish properly.")
        else:
            print("Experiment sequence completed successfully.")
        return True

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

    def reprogram_CAEN(self, kwargs):
        for channel, voltage in self.front_panel_values.items():
            ch_num = self._get_channel_num(channel)
            self.caen.set_voltage(ch_num, voltage)
            print(f"→ {channel}: {voltage:.2f} V")
            logger.info(f"[CAEN] Setting {channel} to {voltage:.2f} V (manual mode)")

# --------------------contants
BLUE = '#66D9EF'