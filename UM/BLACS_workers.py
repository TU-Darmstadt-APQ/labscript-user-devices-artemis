from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import serial
from user_devices.logger_config import logger
import h5py
import threading
from zprocess import rich_print
from zprocess import rich_print
from datetime import datetime
import time

class UMWorker(Worker):
    # NOTE: should stay consistent with tab bases
    MIN_VAL = -28
    MAX_VAL = 0
    def init(self):
        """Initialises communication with the device. When BLACS (re)starts"""
        self.min_val = self.MIN_VAL
        self.max_val = self.MAX_VAL
        self.mode = "ULTRA"

        # for running the buffered experiment in a separate thread:
        self.thread = None
        self._stop_event = threading.Event()
        self._finished_event = threading.Event()

        try:
            # Try to establish a serial connection
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"[UM] UM Serial connection opened on {self.port} at {self.baud_rate} bps")

            # Identify the device
            self.send_to_UM("IDN\r")
            self.device_serial_number  = self.receive_from_UM()
            print(f"Device response to IDN: {self.device_serial_number}")
            
        except Exception as e:
            raise RuntimeError(f"An error occurred during worker initialization: {e}")
    
    def shutdown(self):
        # Should be done when Blacs is closed
        self.connection.close()
        
    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs at the end of the shot."""
        
        print(f"front panel values: {front_panel_values}")

        return front_panel_values

    def check_remote_values(self): # reads the current settings of the device, updating the BLACS_tab widgets
        return

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


    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. 
        Runs at the end of the shot."""
        rich_print(f"---------- Begin transition to Manual: ----------", color=BLUE)

        return True
    
    def send_to_UM(self, cmd_str):
        logger.debug(f"[UM] Sending to UM: {cmd_str}")
        self.connection.write((cmd_str + '\r').encode())
        
    def receive_from_UM(self):
        response = self.connection.readline().decode('utf-8').strip() 
        logger.debug(f"[UM] Received from UM: {response}")
        return response

    def set_voltage(self, channel, voltage):
        if self._extract_channel_name(channel).isdigit():
            channel = self._map_channel_to_number("ADD_ON", channel)  # '01'
        else:
            channel = self._map_channel_to_number(self.mode, channel) # '02'
        voltage = self._format_voltage_value(self.mode, voltage)
        cmd = f"{self.device_name} CH{channel} {voltage}"
        self.send_to_UM(cmd)
        response = self.receive_from_UM()
        logger.debug(f"[UM] Sent: {cmd} \t Received: {response}")
    
    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

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
                    self.set_voltage(conn_name, voltage)
                    self.final_values[conn_name] = voltage
                    print(f"[{t:.3f}s] --> Set {conn_name} (#{conn_name}) = {voltage}")
                    if self._stop_event.is_set():
                        return
        finally:
            self._finished_event.set()
            print(f"[Thread] finished all events !")

    def _scale_to_range(self, normalized_value, min_val, max_val):
        """Convert a normalized value (0 to 1) to the range [min_val, max_val]."""
        min_val = float(min_val)
        max_val = float(max_val)
        if not (0 <= normalized_value <= 1):
            raise ValueError(f"Normalized value {normalized_value} must be between 0 and 1.")
        return normalized_value * (max_val - min_val) + min_val

    def _scale_to_normalized(self, actual_value, min_val, max_val):
        """Normalize a value from [min_val, max_val] to [0, 1]."""
        min_val = float(min_val)
        max_val = float(max_val)
        if not (min_val <= actual_value <= max_val):
            raise ValueError(f"Value {actual_value} out of range [{min_val}, {max_val}]")
        return (actual_value - min_val) / (max_val - min_val)

    def change_mode(self, selected_mode):
        if isinstance(selected_mode, list):
            selected_mode = selected_mode[0]
            print(f"MODE CHANGED: [{selected_mode}]")
            self.mode = selected_mode

    def _extract_channel_name(self, channel: str) -> str:
        """
        Extract the logical channel name from a string like 'CH A'', 'A', '10', etc.,"""
        channel = channel[-2:].strip()

        if channel in {"A", "A'", "B", "B'", "C", "C'"}:
            return channel
        if channel.isdigit():
            if 1 <= int(channel) <= 10:
                return channel
            else:
                raise ValueError(f"Add-on channel '{channel}' out of supported range (1–10)")

        raise ValueError(f"Unrecognized channel format: '{channel}'")

    def _map_channel_to_number(self, mode, channel):
        """
        channel may have forms like "CH A'", "A"
            CHXX:
                01 - A', fast mode      19 - A', precision mode
                03 - B'                 20 - B'
                05 - C'                 21 - C'
                ...
                06 - add-on 9
                07 - add-on 10
                08 - add-on 1
                ...
                15 - add-on 8
        Returns:
             str: The 2-character string of channel number
        """
        channel_name = self._extract_channel_name(channel) # channel = "CH. X", where X can be A, B or C
        channel_mapping = {
            "ULTRA": {"A": "16", "B": "17", "C": "18", "A'": "19", "B'": "20", "C'": "21"},
            "FAST": {"A": "00", "B": "02", "C": "24", "A'": "01", "B'": "03", "C'": "05"},
            "ADD_ON": {
                "1": "08", "2": "09", "3": "10", "4": "11",
                "5": "12", "6": "13", "7": "14", "8": "15",
                "9": "06", "10": "07"
            }
        }

        try:
            return channel_mapping[mode][channel_name]
        except KeyError as e:
            if mode not in channel_mapping:
                raise ValueError(f"Invalid mode: '{mode}'. Valid modes are: {list(channel_mapping)}")
            raise ValueError(
                f"Invalid channel '{channel_name}' for mode '{mode}'. Valid channels: {list(channel_mapping[mode])}")

    def _format_voltage_value(self, mode: str, value: float) -> str:
        match mode:
            case "ULTRA":
                return f"{value:.7f}"
            case "FAST":
                return f"{value:.4f}"
            case _:
                raise ValueError(f"Unknown mode: {mode}")


# --------------------contants
BLUE = '#66D9EF'