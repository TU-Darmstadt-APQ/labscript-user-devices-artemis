import queue

from anyio import wait_readable
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
        self.current_voltages = {}
        self.configure_device()

        # setting values in separate thread
        self.job_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._setting_loop, daemon=True)
        self.worker_thread.start()

        self.failed_set = False
        self.failed_channels = []

        has_timeout = self.timeout is not None      # polling
        has_decay = self.decay_time is not None     # waiting
        if has_timeout == has_decay:
            raise LabscriptError("Define exactly one of `timeout` or `decay_time`.")
        self.deterministic = has_decay
        if has_decay:
            self.setup_delay_params = {
                'base_delay': self.decay_time,
                'min_delay': 0.01,
                'max_delay': 0.5,
                'down_multiplier': 1.5,
            }

    def configure_device(self):
        """
        1. Enable channels/disable channels
        2. Check status
        3. Set ramp rates for all channels
        4. Monitor control mode and board serial number
        5. Get current voltages
        """
        for ch, status in self.channels_status.items():
            self.caen.enable_channel(ch, status)

        print("#################### CHANNEL STATUS #####################")
        for ch in range(self.ch_num):
            status = self.caen.get_status(channel=ch)
            status_dec_str = self._decode_status(ch, int(status))
            print(status_dec_str)
        print("#########################################################")

        self.caen.set_ramp_up_rate(channel=self.ch_num, rate=self.ramp_up)
        self.caen.set_ramp_down_rate(channel=self.ch_num, rate=self.ramp_down)

        print("Control mode : ", self.caen.monitor_control_mode())
        print("Board serial number : ", self.caen.read_board_serial())
        print("Current voltages: \n ")

        for ch, status in self.channels_status.items():
            if status:
                self.current_voltages[ch] = self.caen.monitor_voltage(ch)
                print(ch, self.current_voltages[ch])

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
        for i in range(self.ch_num):
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
        self.h5file = h5_file  # Store path to h5 to write back from front panel
        self.device_name = device_name

        # Prepare events
        with h5py.File(h5_file, 'r') as hdf5_file:
            group = hdf5_file['devices'][device_name]
            AO_data = group['AO_buffered'][:]

        # get first event, only enabled channels
        first_event = AO_data[0]
        t = first_event['time']
        # target_voltages = {self._get_channel_num(ch): first_event[ch] for ch in first_event.dtype.names if ch!="time" and self.channels_status[self._get_channel_num(ch)]}
        target_voltages = {}
        for ch in first_event.dtype.names:
            if ch == "time":
                continue
            ch_num = self._get_channel_num(ch)
            if not self.channels_status[ch_num]:
                continue
            target_voltages[ch_num] = first_event[ch]


        if self.deterministic:
            wait_time = self._calculate_settling_time(target_voltages)
            rich_print(f"Deterministic wait time: {wait_time*1000:.1f} ms", color=ORANGE)
            job_data = {
                "voltages": target_voltages,
                "wait_time": wait_time,
                "start_time": time.perf_counter()
            }
        else:
            job_data = {
                "voltages": target_voltages,
                "wait_time": 0,
                "start_time": time.perf_counter()
            }

        self.current_voltages = target_voltages.copy()

        self.job_queue.put(job_data)
        self.job_queue.join() # blocks until all task are done

        final_values = {"ch %d" % ch: val for ch, val in target_voltages.items()}
        rich_print(f"---------- End transition to Buffered: ----------", color=BLUE)
        return final_values


    def _setting_loop(self):
        """Process job in a separate thread."""
        while True:
            item = self.job_queue.get()
            if item is None:
                self.job_queue.task_done()
                break

            try:
                self._apply_all_voltages(item['voltages'], item['start_time'])

                if self.deterministic:
                    time.sleep(item['wait_time'])
                    self._validate_settling(item['voltages'])
                else:
                    self._block_until_set(item["voltages"], self.timeout, self.threshold)

            except Exception as e:
                rich_print(f"Error in _setting_loop: {e}", color=RED)
                raise
            finally:
                self.job_queue.task_done()

    def _apply_all_voltages(self, voltages, start_time):
        for channel, voltage in voltages.items():
            self.caen.set_voltage(channel, voltage)
            if not self._check_channel_state(channel): # channel is not settable
                raise LabscriptError(f" {self.device_name}: ch{channel} is OFF or/and disabled. Cannot set voltage={voltage}.")
            else:
                elapsed = time.perf_counter() - (start_time or 0)
                print(f"[{elapsed:.3f}s] ch{channel} = {voltage}")

    def _validate_settling(self, target_voltages):
        for ch, val in target_voltages.items():
            mon = self.caen.monitor_voltage(ch)
            if abs(mon - abs(val)) >= self.threshold:
                self.failed_channels.append((ch, val, mon))

        if len(self.failed_channels) > 0:
            self.failed_set = True
            raise LabscriptError(
                f"Failed to set voltages on {self.device_name}:\n" +
                "\n".join(
                    f"ch{ch}: target={t}, actual={m}"
                    for ch, t, m in self.failed_channels
                )
            )

    def _calculate_settling_time(self, target_voltages):
        current_voltages = self.current_voltages
        max_wait = self.setup_delay_params['min_delay']
        rate_up = self.ramp_up
        rate_down = self.ramp_down
        base_delay = self.setup_delay_params['base_delay']

        for ch, target_v in target_voltages.items():
            prev_v = current_voltages.get(ch, 0)
            delta_v = abs(target_v - prev_v)
            if target_v > prev_v:           # ramp up
                t_ramp = delta_v / rate_up
            else:                           # ramp down
                t_ramp = delta_v / rate_down

            t_settle = (base_delay + t_ramp)
            if target_v < prev_v:           # ramping down usually takes longer
                t_settle *= self.setup_delay_params['down_multiplier']

            t_settle = max(t_settle, self.setup_delay_params['min_delay'])
            t_settle = min(t_settle, self.setup_delay_params['max_delay'])

            if t_settle > max_wait:
                max_wait = t_settle

        return max_wait

    def _block_until_set(self, voltages, timeout, threshold):
        """
        NOTE: Non-deterministic solution
        Block execution until all requested channel voltages are settled or a timeout occurs.

        This method continuously monitors the voltage of each specified channel and compares
        it to the requested target value. A channel is considered "settled" when the absolute
        difference between the monitored voltage and the target voltage is within a fixed
        `threshold`. The method polls the device every 0.01 seconds.

        Parameters
        ----------
        voltages : Dict of channel numbers to target voltages.
        timeout : int, optional (seconds)

        Returns
        -------
        list[tuple[int, float, float]]
            A list of failures in the form `(channel, target_voltage, monitored_voltage)`
            for each channel that did not settle within the timeout.
            Returns an empty list if all channels successfully settled.
        """

        settled = set()
        failed = []
        start = time.monotonic()
        poll_dt = 0.01

        while True:
            for ch, target in voltages.items():
                if ch in settled:
                    continue

                mon = self.caen.monitor_voltage(ch)
                if abs(mon - abs(target)) <= threshold:
                    settled.add(ch)

            if len(settled) == len(voltages): # all channels are settled
                rich_print(" ---- All channels settled ---- ", color=GREEN)
                break

            if time.monotonic() - start >= timeout:  # timeout reached --> collect failures and raise Exception
                self.failed_set = True
                for ch, target in voltages.items():
                    if ch not in settled:
                        mon = self.caen.monitor_voltage(ch)
                        failed.append((ch, target, mon))

                self.failed_channels = failed
                raise LabscriptError(
                    f"Failed to set voltages on {self.device_name}. Timeout {timeout} exceeded :\n" +
                    "\n".join(
                        f"ch{ch}: target={t}, actual={m}"
                        for ch, t, m in failed
                    )
                )

            time.sleep(poll_dt)

    def _get_channel_num(self, channel: str) -> int:
        ch_lower = channel.lower()
        if ch_lower.startswith("ch "):
            channel_num = int(ch_lower[3:].strip())  # 'ch 0', 'ch 3', 'ch 7' -> 0, 3, 7
            return channel_num
        elif ch_lower.startswith("ch"):
            channel_num = int(ch_lower[2:].strip())  # 'ch0', 'ch03', 'ch7' -> 0, 3, 7
            return channel_num
        elif ch_lower.startswith("ao "):
            channel_num = int(ch_lower[3:])  # 'ao 3' -> 3
            return channel_num
        elif ch_lower.startswith("ao"):
            channel_num = int(ch_lower[2:])  # 'ao3' -> 3
            return channel_num
        elif ch_lower.startswith("channel"):
            _, channel_num_str = channel.split()  # 'channel 1' -> 1
            channel_num = int(channel_num_str)
            return channel_num
        else:
            raise ValueError(f"Unexpected channel name format: '{channel}'")

    def _decode_status(self, ch:int, st:int) -> str:
        status = f"Channel {ch}: "
        # print(f"[DEBUG]: status: {repr(bits16)}, {bits16}")

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
        if self.failed_set:
            with h5py.File(self.h5file, 'r+') as hdf5_file:
                group = hdf5_file['devices'][self.device_name]
                group.attrs['failed_set'] = self.failed_set
                group.attrs['failed_channels'] = self.failed_channels

        self.failed_set = False
        self.failed_channels = []

        return True

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

    def reprogram_CAEN(self, kwargs):
        rich_print("Reprogramming...", color=BLUE)
        for channel, voltage in self.front_panel_values.items():
            ch_num = self._get_channel_num(channel)
            self.caen.set_voltage(ch_num, voltage)
            # store the values from manual to hdf5 file.
            if not self._check_channel_state(ch_num):  # channel is not settable
                rich_print(f"CH{ch_num} = {voltage} is OFF or/and disabled.", color=ORANGE)
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
        """Returns True is channel is ON and not disabled."""
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
YELLOW = '#F5E727'
RED = '#F52727'