from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab

class BNC_575Tab(DeviceTab):
     # Capabilities
    # base_units = {'freq':'MHz', 'amp':'dBm'}
    # base_min = {'freq':0.1,   'amp':-140}
    # base_max = {'freq':1057.5,  'amp':20}
    # base_step = {'freq':1,    'amp':0.1}
    # base_decimals = {'freq':6, 'amp':1}
    def initialise_GUI(self):
        #TODO: create custom PulseOutput and corresponded widgets
    
    def initialise_workers(self):
        # Get properties from connection table
        device = self.settings['connection_table'].find_by_name(self.device_name)
        if device is None:
            raise ValueError(f"Device '{self.device_name}' not found in the connection table.")
        
        # Look up a the connection table for device properties
        port = device.properties["port"]
        baud_rate = device.properties["baud_rate"]
        
        worker_kwargs = {
            "name": self.device_name + '_main',
            "port": port,
            "baud_rate": baud_rate,
        }
        
        self.create_worker(
            'main_worker',
            'user_devices.BNC_575.BLACS_workers.BNC_575Worker',
            worker_kwargs,
            )
        
        self.primary_worker = "main_worker"
        
