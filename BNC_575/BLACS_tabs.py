from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab

class BNC_575Tab(DeviceTab):
    def initialise_GUI(self):
        #TODO
        self.base_units =   {'delay': 'ms',     'width': 'ms',              'state': 'State'}
        self.base_min =     {'delay': 0,        'width': 10 * 10.0**(-6),   'state': 0}
        self.base_max =     {'delay': 999.99999999975, 'width': 999.99999999975, 'state': 1}
        self.base_step =    {'delay': 0.01,     'width': 0.01,              'state': 1}
        self.base_decimals ={'delay': 6,        'width': 6,                 'state': 0}  # TODO: find out what the state precision is!
        self.num_DDS = 8 # i guess so

        dds_prop = {}
        for i in range(self.num_DDS):
            dds_prop['channel %d' % i] = {}
            for subch in ['delay', 'width', 'state']:
                dds_prop['channel %d' % i][subch] = {
                    'base_unit': self.base_units[subch],
                    'min': self.base_min[subch],
                    'max': self.base_max[subch],
                    'step': self.base_step[subch],
                    'decimals': self.base_decimals[subch]
                }
            
        self.create_dds_outputs(dds_prop)
        dds_widgets, ao_widgets, do_widgets = self.auto_create_widgets()
        self.auto_place_widgets(("DDS outputs", dds_widgets))

        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)
    
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
        
