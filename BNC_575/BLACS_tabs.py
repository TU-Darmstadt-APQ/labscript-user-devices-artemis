from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab

class BNC_575Tab(DeviceTab):
    def initialise_GUI(self):
        connection_table = self.settings['connection_table']
        properties = connection_table.find_by_name(self.device_name).properties

        num_AO = properties.get('num_AO', 8)

        do_prop = {}
        for i in range(self.num_DO): # do the flags correspond to digital output?
            do_prop['flag %d' % i] = {}

        # Create the output objects
        self.create_digital_outputs(do_prop)
        # Create widgets for output objects
        dds_widgets, ao_widgets, do_widgets = self.auto_create_widgets()
        self.auto_place_widgets(("Flags", do_widgets))

        # channel_names = [f'ch{i}' for i in range(num_AO)]
        # pulse_params = {}
        # for ch in channel_names:
        #     pulse_params[ch] = {
        #         'delay': {
        #             'base_unit': 'ns',
        #             'min': 0,
        #             'max': 1e9,
        #             'step': 1,
        #             'decimals': 0
        #         },
        #         'width': {
        #             'base_unit': 'ns',
        #             'min': 1,
        #             'max': 1e9,
        #             'step': 1,
        #             'decimals': 0
        #         },
        #         'period': {
        #             'base_unit': 'ns',
        #             'min': 10,
        #             'max': 1e9,
        #             'step': 10,
        #             'decimals': 0
        #         },
        #         'polarity': {
        #             'enum': ['Positive', 'Negative']
        #         },
        #         'state': {
        #             'type': 'bool'
        #         }
        #     }
        # self.create_digital_outputs(pulse_params)
        #
        # widgets = self.auto_create_widgets()

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
        
