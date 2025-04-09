from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from qtutils import UiLoader
from user_devices.logger_config import logger

class UMTab(DeviceTab):
    """to define device capabilities and generate the GUI for manual control of the device through the front panel"""
    def initialize_GUI(self):

        # Define capabilities 
        self.base_units = 'V'
        self.base_min = 0 
        self.base_max = 28 # TODO: What is the maximum?
        self.base_step = 1
        self.base_decimals = 6
        self.num_AO = 3 # Three for secondary channels

        ao_prop = {
            'CH. A': {
                'base_unit': self.base_units,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals,
            },
            'CH. B': {
                'base_unit': self.base_units,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals,
            },
            'CH. C': {
                'base_unit': self.base_units,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals,
            },
        }
        
        # Create the output objects
        # It will have automatically looked up relevant entries in the BLACS connection table to get their name and unit conversion. 
        # TODO: how it is connected to connection table, wat should be defined there?
        self.create_analog_outputs(ao_prop)
        
        # Create widgets for output objects
        dds_widgets, ao_widgets, do_widgets = self.auto_create_widgets()
        self.auto_place_widgets(("Secondary channels", ao_widgets))

        # Accessing the Qt Layout which contains the main body of the tab 
        self.get_tab_layout()
        
        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False) # see at 3.3.19, 5.3 (docs) 

    def initialise_workers(self):
        """ Tells the device Tab to launch one or more worker processes to communicate with the device."""
        # Get properties from connection table.
        device = self.settings['connection_table'].find_by_name(self.device_name)
        
        # look up the port and baud in the connection table
        port = device.properties["port"]
        baud_rate = device.properties["baud_rate"]
        
        # Start a worker process 
        self.create_worker(
            'main_worker',
            'user_devices.UM.BLACS_workers.UMWorker',
            {"port": port, "baud_rate": baud_rate} # All connection table properties should be added 
            )
        self.primary_worker = "main_worker"

