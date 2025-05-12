from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import serial
from qtutils.outputbox import PURPLE
from user_devices.logger_config import logger
import time
import h5py
from labscript_utils import properties
from zprocess import rich_print

"""
This class is for communication with hardware 
"""
class BS110Worker(Worker):
    def init(self):
        """Initialises communication with the device. When BLACS (re)starts"""
        self.final_values = {}
        try:
            # Try to establish a serial connection
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"Connected to BS110 on {self.port} with baud rate {self.baud_rate}")
            
            # Send IDN (identify) command to identify the device
            self.send_to_BS("IDN\r")
            device_info = self.receive_from_BS().split()
            logger.debug(f"Receiving identification BS-110: {device_info}")
            print(f"Device response: {device_info}")

            # Parse the response from the device 
            if len(device_info) >= 4:
                self.device_serial = device_info[0]  # For example, 'HV023'
                self.device_voltage_range = device_info[1]  # For example, '50'
                self.device_channels = device_info[2]  # For example, '16'
                self.device_output_type = device_info[3]  # For example, 'b' (bipolar, unipolar, quadrupole, steerer supply)
                logger.info(f"Device Serial: {self.device_serial}, Voltage Range: {self.device_voltage_range}, Channels: {self.device_channels}, Output Type: {self.device_output_type}")
            else:
                raise RuntimeError("Failed to parse the device identification string.")
        
        except Exception as e:
            raise RuntimeError(f"An error occurred during initialization: {e}")
        
        
    def shutdown(self):
        # Should be done when Blacs is closed
        self.connection.close()
    
    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs outside of the shot."""
        # TODO: Optimise so that only items that have changed are reprogrammed by storing the last programmed values
        # TODO: Store manual values to h5 file

        rich_print(f"---------- Manual MODE start: ----------", color=PURPLE)
        print("Front panel values (before shot):")
        for ch_name, voltage in front_panel_values.items():
            print(f"  {ch_name}: {voltage:.2f} V")

        # Set values after the shot to front panel
        if self.final_values and not getattr(self, 'restored_from_final_values', False):
            for ch_name, value in self.final_values.items():
                ch_num = self._get_channel_num(ch_name)
                front_panel_values[f'channel {int(ch_num)}'] = value
            self.restored_from_final_values = True  # Flag if already restored

        print("\nFront panel values (after shot):")
        for ch_name, voltage in self.final_values.items():
            print(f"  {ch_name}: {voltage:.2f} V")

        self.final_values = {} # Empty after restoring

        # Program the device for each channel
        print("\nProgramming the device with the following values:")
        print("----------DEBUG------------")
        for channel_num in range(int(self.device_channels)):
            channel_name = f'channel {channel_num}'

            voltage = front_panel_values.get(channel_name, 0.0)  # Get voltage, defaulting to 0 if not found
            print(f"channel name: {channel_name}, \t voltage: {voltage}")
            self._program_manual(channel_num, voltage)

        # # Update final values
        # for ch_name, value in front_panel_values.items():
        #     ch_num = self._get_channel_num(ch_name)
        #     self.final_values[f"ao{ch_num}"] = value
        # for ch_name, voltage in self.final_values.items():
        #     print(f"{ch_name:<6}: {voltage:.2f} V")

        rich_print(f"---------- Manual MODE end: ----------", color=PURPLE)
        return front_panel_values

    def _program_manual(self, channel_num, value):
        """Helper function to send the voltage value to the BS-110 device.
        Args:
            channel_num (int)
            value (float)
            """
        channel = f"CH{int(channel_num):02d}"
        scaled_voltage = self._scale_to_normalized(float(value), float(self.device_voltage_range))

        sendStr = f"{self.device_serial} {channel} {scaled_voltage:.6f}\r"
        self.send_to_BS(sendStr)

        #DEBUG
        denormalized_voltage = self._scale_to_range(float(scaled_voltage), float(self.device_voltage_range))
        print(f"Sent to BS-110 from front panel (manual mode): {sendStr.strip()} with {denormalized_voltage:.2f} V")
        logger.info(f"Sent to BS-110 from front panel (manual mode): {sendStr.strip()} with {denormalized_voltage:.2f} V")

        receiveStr = self.receive_from_BS().strip()

        print(f"Received from BS-110 to front panel in manual mode: {receiveStr.rstrip()} "
                f"comparing  to '{channel} {scaled_voltage:.6f}'")
        expected = f'{channel} {scaled_voltage:.6f}'
        if receiveStr.strip() != expected:
            print(f"Mismatch!\nExpected: {repr(expected)}\nReceived: {repr(receiveStr.strip())}")
            raise Exception(f'Failed to execute command: {sendStr}')

    def _get_channel_num(self, channel):
        """Gets channel number with leading zeros 'XX' from strings like 'AOX' or 'channel X'.
        Args:
            channel (str): The name of the channel, e.g. 'AO0', 'AO12', or 'channel 3'.

        Returns:
            str: Two-digit channel number as string, e.g. '01', '12'."""
        ch_lower = channel.lower()
        if ch_lower.startswith("ao"):
            channel_num = channel[2:]  # 'ao3' -> '3'
        elif ch_lower.startswith("channel"):
            _, channel_num = channel.split()  # 'channel 1' -> '1'
        else:
            raise LabscriptError(f"Unexpected channel name format: '{channel}'")

        channel_int = int(channel_num)
        return f"{channel_int:02d}"

    def check_remote_values(self): # reads the current settings of the device, updating the BLACS_tab widgets 
        #no need, since no such a command for BS 110
        return

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh): 
        """transitions the device to buffered shot mode, 
        reading the shot h5 file and taking the saved instructions from 
        labscript_device.generate_code and sending the appropriate commands 
        to the hardware. 
        Runs at the start of each shot."""
        # Get device properties
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.restored_from_final_values = False # drop the flag

        self.initial_values = initial_values # Store the initial values in case we have to abort and restore them
        self.final_values = {}  # Store the final values to update GUI during transition_to_manual
        AO_data = None
        self.h5file = h5_file

        with h5py.File(h5_file, 'r') as hdf5_file: # read only
            group = hdf5_file['devices'][device_name]
            AO_data = group['AO'][:]
            self.device_prop = properties.get(hdf5_file, device_name, 'device_properties')
            print("======== Device Properties : ", self.device_prop, "=========")

        for row in AO_data:
            time = row["time"]
            print (f"\n time={time}")
            for channel_name in row.dtype.names:
                if channel_name.lower() == 'time':
                    continue  # Skip the time column

                voltage = row[channel_name]
                channel_num = self._get_channel_num(channel_name)
                scaled = self._scale_to_normalized(voltage, self.device_voltage_range)

                sendStr = f"{self.device_serial} CH{channel_num} {scaled:.6f}\r"
                print(f"→ Channel: {channel_name} (#{channel_num}), Voltage: {voltage}, Scaled: {scaled}")
                self.send_to_BS(sendStr)
                self.receive_from_BS() # Do not store the responses in the serial buffer.
                self.final_values[channel_name] = voltage

        rich_print(f"---------- End transition to Buffered: ----------", color=BLUE)
        return
        

    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. 
        Runs at the end of the shot."""
        rich_print(f"---------- Begin transition to Manual: ----------", color=BLUE)
        print("\nFinal Values After Shot:")
        print("-------------------------")
        for ch_name, voltage in self.final_values.items():
            print(f"{ch_name:<6}: {voltage:.2f} V")

        rich_print(f"---------- End transition to Manual: ----------", color=BLUE)
        return True

    def send_to_BS(self, sendStr):
        logger.debug(f"Sending to BS110: {sendStr}")
        self.connection.reset_input_buffer()
        # print(f"Sending to BS110: {sendStr}")
        self.connection.write(sendStr.encode())
        
        
    def receive_from_BS(self):
        response = self.connection.readline().decode().strip() # assuming utf-8 encoding
        logger.debug(f"Received from device: {response}")
        # print(f"Received from device: {response}")
        return(response)
    
    def abort_transition_to_buffered(self):
        # return self.transition_to_manual()
        try:
            print(f"Aborting transition to buffered.")
            return self.transition_to_manual()
        except Exception as e:
            print(f"Failed to abort properly: {e}")
            return

    def _scale_to_range(self, normalized_value, max_range):
        """Convert a normalized value (0 to 1) to the specified range (-max_range to +max_range)"""
        max_range = float(max_range)
        return 2 * max_range * normalized_value - max_range

    def _scale_to_normalized(self, actual_value, max_range):
        """Convert an actual value (within -max_range to +max_range) to a normalized value (0 to 1)"""
        max_range = float(max_range)
        return (actual_value + max_range) / (2 * max_range)

# ------------------ constants
BLUE = '#66D9EF'
PURPLE = '#A020F0'