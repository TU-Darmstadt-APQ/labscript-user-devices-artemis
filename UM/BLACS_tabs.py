from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from qtutils import UiLoader
from user_devices.logger_config import logger

class UMTab(DeviceTab):
    def initialize_GUI(self):
        logger.debug(f"initializaing GUI :)))))")
        # self.mode_dropdown = self.create_dropdown(
        # name="Mode",
        # choices=["FAST", "ULTRA"],
        # default="ULTRA"
        # )
        # self.auto_place_widgets(("Operation Mode", [self.mode_dropdown]))

        # Trying new UI for modes
        self.base_mode = 'Mode'
        self.fast_mode = 'FAST'
        self.ultra_mode = 'ULTRA'

        mode_prop = {
            'base_mode': self.base_units,
            'fast_mode': self.fast_mode,
            'ultra_mode': self.ultra_mode,
        }

        # Capabilities
        self.base_units = 'V'
        self.base_min = 0 
        self.base_max = 28 # TODO: What is the maximum?
        self.base_step = 1
        self.base_decimals = 6
        self.num_AO = 3 # Three for secondary channels

        ao_prop = {}
        ao_prop['CH. A'] = {
                'base_unit': self.base_units,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals,
            }
        ao_prop['CH. B'] = {
                'base_unit': self.base_units,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals,
            }
        ao_prop['CH. C'] = {
                'base_unit': self.base_units,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals,
            }
        

        # Create the output objects
        self.create_analog_outputs(ao_prop)
        self.create_digital_outputs(mode_prop)
        
        # Create widgets for output objects
        widgets, ao_widgets, do_widgets = self.auto_create_widgets()
        self.auto_place_widgets(("Secondary channels", ao_widgets))
        self.auto_place_widgets(("Modes", do_widgets))
        self.auto_place_widgets(widgets)
        
        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)

    def initialise_workers(self):
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

    def change_mode(self, index):
        # TODO: Where to change the attributs?
        mode = self.mode_dropdown.currentText()
        if mode == "FAST":
            self.base_decimals = 7
            self.send_to_UM
        