from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab

class BS_341ATab(DeviceTab):
    def initialise_GUI(self):
        # Capabilities
        self.base_units = 'V'
        self.base_min = -5 # TODO: What is the range?
        self.base_max = 5
        self.base_step = 1
        self.base_decimals = 3
        self.num_AO = 4
        
        print("initialize_GUI is called")
        
        # Create AO Output objects
        ao_prop = {}
        for i in range(self.num_AO):
            ao_prop['CH%d' % i] = {
                'base_unit': self.base_units,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals,
            }
            
        # Create the output objects
        self.create_analog_outputs(ao_prop)
        
        # Create widgets for output objects
        widgets, ao_widgets,_ = self.auto_create_widgets()
        self.auto_place_widgets(("Analog Outputs", ao_widgets))
        self.auto_place_widgets(widgets)
        
        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)
        
    
    def initialise_workers(self):
        # Get properties from connection table.
        device = self.settings['connection_table'].find_by_name(self.device_name)
        if device is None:
            raise ValueError(f"Device '{self.device_name}' not found in the connection table.")
           
        # look up the port and baud in the connection table
        port = device.properties["port"]
        baud_rate = device.properties["baud_rate"]
        
        if baud_rate is None:
            raise KeyError(f"Missing baud_rate in device prop")
        if port is None:
            raise KeyError(f"Missing port in device prop")
        
        
        # Start a worker process 
        self.create_worker(
            'main_worker',
            'user_devices.BS_341A.BLACS_workers.BS_341AWorker',
            {"port": port, "baud_rate": baud_rate} # all connection table properties should be added 
            )
        self.primary_worker = "main_worker"
        
