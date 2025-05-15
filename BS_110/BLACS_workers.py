from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import serial
from qtutils.outputbox import PURPLE
from user_devices.logger_config import logger
import time
import h5py
from labscript_utils import properties
from zprocess import rich_print
from datetime import datetime
import numpy as np

"""
This class is for communication with hardware 
"""
class BS110Worker(Worker):

    def init(self):
        """Initialises communication with the BS-1-10 device via BiasSupply abstraction."""
        self.final_values = {} #[[channel_nums(ints)],[voltages(floats)]]
        self.verbose = True

        try:
            from .bias_supply import BiasSupply
            self.bias_supply = BiasSupply(self.port, self.baud_rate, verbose=self.verbose)

            # Get device information
            self.device_serial = self.bias_supply.device_serial # For example, 'HV023'
            self.device_voltage_range = self.bias_supply.device_voltage_range # For example, '50'
            self.device_channels = self.bias_supply.device_channels # For example, '10'
            self.device_output_type = self.bias_supply.device_output_type# For example, 'b' (bipolar, unipolar, quadrupole, steerer supply)

            logger.info(
                f"Connected to BS-1-10 on {self.port} with baud rate {self.baud_rate}\n"
                f"Device Serial: {self.device_serial}, Voltage Range: {self.device_voltage_range}, "
                f"Channels: {self.device_channels}, Output Type: {self.device_output_type}"
            )

        except LabscriptError as e:
            raise RuntimeError(f"BS-1-10 identification failed: {e}")
        except Exception as e:
            raise RuntimeError(f"An error occurred during BS110Worker initialization: {e}")

        
        
    def shutdown(self):
        # Should be done when Blacs is closed
        self.connection.close()

    def program_manual(self, front_panel_values):
        """
        Allows user control of the device via the BLACS tab.
        Sets device outputs to the values from front panel widgets.
        Runs outside of the shot.
        """
        rich_print(f"---------- Manual MODE start: ----------", color=PURPLE)
        self.front_panel_values = front_panel_values

        if self.verbose is True:
            print("Front panel values (before shot):")
            for ch_name, voltage in front_panel_values.items():
                print(f"  {ch_name}: {voltage:.2f} V")

        # Restore final values from previous shot, if available
        if self.final_values and not getattr(self, 'restored_from_final_values', False):
            for ch_num, value in self.final_values.items():
                front_panel_values[f'channel {int(ch_num)}'] = value
            self.restored_from_final_values = True

        if self.verbose is True:
            print("\nFront panel values (after shot):")
            for ch_name, voltage in self.final_values.items():
                print(f"  {ch_name}: {voltage:.2f} V")

        self.final_values = {}# Empty after restoring

        return front_panel_values

    def _program_manual(self, front_panel_values):
        """Sends voltage values to the device for all channels using BiasSupply.
        """
        if self.verbose is True:
            print("\nProgramming the device with the following values:")
            logger.info("Programming the device from manual with the following values:")

        for channel_num in range(int(self.num_AO)):
            channel_name = f'channel {channel_num}'
            voltage = front_panel_values.get(channel_name, 0.0)
            if self.verbose is True:
                print(f"→ {channel_name}: {voltage:.2f} V")
                # logger.info(f"Setting {channel_name} to {voltage:.2f} V (manual mode)")
            self.bias_supply.set_voltage(channel_num, voltage)

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
        """
        Transitions the device to buffered shot mode. Reads the shot h5 file and takes the saved instructions from
        labscript_device.generate_code and sends the appropriate commands to the hardware.
        Runs at the start of each shot.

        Args:
            device_name (str): Name of the device.
            h5_file (str): Path to the HDF5 shot file.
            initial_values (dict): Initial values before the shot.
            fresh (bool): Indicates whether the shot is fresh or resumed.
        """
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.restored_from_final_values = False # Drop flag
        self.initial_values = initial_values # Store the initial values in case we have to abort and restore them
        self.final_values = {} # Store the final values to update GUI during transition_to_manual
        self.h5file = h5_file
        self.device_name = device_name

        with h5py.File(h5_file, 'r') as hdf5_file:
            group = hdf5_file['devices'][device_name]
            AO_data = group['AO'][:]
            self.device_prop = properties.get(hdf5_file, device_name, 'device_properties')
            print("======== Device Properties : ", self.device_prop, "=========")

        for row in AO_data:
            if self.verbose is True:
                time = row["time"]
                print(f"\n time = {time}")
                logger.info(f"Programming the device from buffered at time {time} with following values")

            for channel_name in row.dtype.names:
                if channel_name.lower() == 'time': # Skip the time column
                    continue

                voltage = row[channel_name]
                channel_num = self._get_channel_num(channel_name)
                self.bias_supply.set_voltage(channel_num, voltage)

                if self.verbose is True:
                    print(f"→ Channel: {channel_name} (#{channel_num}), Voltage: {voltage}")

                # Store the values
                self.final_values[channel_num] = voltage

        rich_print(f"---------- End transition to Buffered: ----------", color=BLUE)
        return

    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. 
        Runs at the end of the shot."""
        # rich_print(f"---------- Begin transition to Manual: ----------", color=BLUE)
        # print("\nFinal Values After Shot:")
        # print("-------------------------")
        # for ch_num, voltage in self.final_values.items():
        #     print(f"channel {ch_num}: {voltage:.2f} V")
        #
        # rich_print(f"---------- End transition to Manual: ----------", color=BLUE)
        return True

    def abort_transition_to_buffered(self):
        # return self.transition_to_manual()
        try:
            print(f"Aborting transition to buffered.")
            return self.transition_to_manual()
        except Exception as e:
            print(f"Failed to abort properly: {e}")
            return

    def send_to_BS(self, kwargs):
        """Sends manual values from the front panel to the BS-1-10 device.
            This function is executed in the worker process. It uses the current
            front panel values to reprogram the device in manual mode by clicking the button 'send to device'.
            Args:
                kwargs (dict): Not used currently.
            """
        # TODO: Store manual values to h5 file
        self._program_manual(self.front_panel_values)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._append_front_panel_values_to_manual(self.front_panel_values, current_time)

    def _append_front_panel_values_to_manual(self, front_panel_values, current_time):
        """
            Append front-panel voltage values to the 'AO_manual' dataset in the HDF5 file.

            This method records the current manual voltage settings (from the front panel)
            along with a timestamp into the 'AO_manual' table inside the device's HDF5 group.
            It assumes that `self.h5file` and `self.device_name` have been set
            (in `transition_to_buffered`). If not, a RuntimeError is raised.

            Parameters
            ----------
            front_panel_values : dict
                Dictionary mapping channel names (e.g., 'channel 0') to voltage values (float).
            current_time : str
                The timestamp (formatted as a string) when the values were recorded

            Raises
            ------
            RuntimeError
                If `self.h5file` is not set (i.e., manual values are being saved before
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
            # print("Keys in group:", list(group.keys()))

            dset = group['AO_manual']
            old_shape = dset.shape[0]
            dtype = dset.dtype
            connections = [name for name in dset.dtype.names if name != 'time'] #'ao1'

            # Create new data row
            new_row = np.zeros((1,), dtype=dtype)
            new_row['time'] = current_time
            for conn in connections:
                channel_name = self._ao_to_channel_name(conn)
                new_row[conn] = front_panel_values.get(channel_name, 0.0)

            # Add new row to table
            dset.resize(old_shape + 1, axis=0)
            dset[old_shape] = new_row[0]

    @staticmethod
    def _ao_to_channel_name(ao_name: str) -> str:
        """ Convert 'ao0' to 'channel 0' """
        try:
            channel_index = int(ao_name.replace('ao', ''))
            return f'channel {channel_index}'
        except ValueError:
            raise ValueError(f"Impossible to convert from '{ao_name}'")

    @staticmethod
    def _channel_name_to_ao(channel_name: str) -> str:
        """ Convert 'channel 0' to 'ao0' """
        try:
            channel_index = int(channel_name.replace('channel ', ''))
            return f'ao{channel_index}'
        except ValueError:
            raise ValueError(f"Impossible to convert from '{channel_name}'")


# ------------------ constants
BLUE = '#66D9EF'
PURPLE = '#A020F0'