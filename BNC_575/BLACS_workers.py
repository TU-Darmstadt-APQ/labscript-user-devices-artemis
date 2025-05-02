import labscript_utils.h5_lock # TODO: im not sure if it this neccessary and what it does exactly
import h5py
import serial
import numpy as np
from blacs.tab_base_classes import Worker
from labscript import LabscriptError
from labscript_utils import properties


from user_devices.logger_config import logger
import time


class BNC_575Worker(Worker):
    def init(self):
        """Initializes connection to BNC_575 device (USB pretending to be virtual COM port)"""

        try:
            # self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            # logger.debug("<trying to initialise pulse Generator  directly in workers>")
            from .pulse_generator import PulseGenerator
            self.generator = PulseGenerator(self.port, self.baud_rate, verbose=False)
            logger.info(f"Pulse Generator Serial connection opened on {self.port} at {self.baud_rate} bps")
        except Exception as e:
            raise LabscriptError(f"Serial connection failed: {e}")
           
    def shutdown(self):
        # Should be done when Blacs is closed
        self.connection.close()

    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs at the end of the shot.
        setting the pulse width, delay and period --> ok\r\n
        """
        print(f"front panel values: {front_panel_values}")
        self.check_remote_values()

    def check_remote_values(self): # reads the current settings of the device, updating the BLACS_tab widgets 
        return

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh): 
        """transitions the device to buffered shot mode, 
        reading the shot h5 file and taking the saved instructions from 
        labscript_device.generate_code and sending the appropriate commands 
        to the hardware. 
        Runs at the start of each shot."""
        # Get device properties
        print(f"---------- Begin transition to Buffered: ----------")

        self.h5file = h5_file
        with h5py.File(h5_file, 'r') as hdf5_file: # read only
            group = hdf5_file['devices'][device_name]
            self.device_prop = properties.get(hdf5_file, device_name, 'device_properties')
            print("======== Device Properties : ", self.device_prop, "=========")

        # Setting the pulse generator
        # TODO:
        self.generator.disable_trigger()
        self.generator.start_pulses()
        self.generator.enable_output(2)
        self.generator.set_delay(2, 3)
        self.generator.set_width(2, 2)

        print(f"---------- END transition to Buffered: ----------")
        return


    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. Transition to manual mode after buffered execution completion.

        Returns:
            bool: `True` if transition to manual is successful.
        """
        print(f"---------- Begin transition to Manual: ----------")
        data = np.empty(5, dtype='<U20')
        data = [f"Stringing {d}" for d in [1, 2, 3, 4, 5]]

        with h5py.File(self.h5file, 'r+') as hdf_file:
            if '/data' not in hdf_file:
                group = hdf_file.create_group('/data')
            else:
                group = hdf_file['/data']

            if self.device_name in group:
                print(f"Dataset {self.device_name} already exists. Overwriting.")
                del group[self.device_name]

        print(f"---------- END transition to Manual: ----------")
        return True

    def abort_transition_to_buffered(self):
        try:
            print(f"Aborting transition to buffered.")
            return self.transition_to_manual()
        except Exception as e:
            print(f"Failed to abort properly: {e}")
            return

    def abort_buffered(self):
        """Aborts a currently running buffered execution.

        Returns:
            bool: `True` is abort was successful.
        """
        # self.intf.send_command_ok('abt')
        # # loop until abort complete
        # while self.intf.status()[0] != 5:
        #     time.sleep(0.5)
        # return True

    
        