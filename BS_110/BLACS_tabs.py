from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab

class BS110Tab(DeviceTab):
    def initialise_GUI(self):
        # Capabilities
        self.base_units = 'V'
        self.base_min = -50 # TODO: What is the range?
        self.base_max = 50
        self.base_step = 1
        self.base_decimals = 3 
        self.num_AO = 3
        
        print("initialize_GUI is called")
        
        # Create AO Output objects
        ao_prop = {}
        for i in range(self.num_AO):
            ao_prop['channel %d' % i] = {
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
        
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)
    
    
    def initialise_workers(self):
        # Get properties from connection table.
        device = self.settings['connection_table'].find_by_name(self.device_name)
        
        # look up the port and baud in the connection table
        port = device.properties["port"]
        baud_rate = device.properties["baud_rate"]
        worker_kwargs = {"name": self.device_name + '_main',
                          "port": port,
                          "baud_rate": baud_rate
                          }
        
        self.create_worker(
            'main_worker',
            'user_devices.BS_110.BLACS_workers.BS110Worker',
            worker_kwargs, 
            )
        self.primary_worker = "main_worker"
        
