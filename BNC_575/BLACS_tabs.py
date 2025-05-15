from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab

class BNC_575Tab(DeviceTab):
    def initialise_GUI(self):
        # TODO: We may want to add start/stop/reset buttons to GUI
        connection_table = self.settings['connection_table']
        properties = connection_table.find_by_name(self.device_name).properties

        num_AO = properties.get('num_AO', 8)
        do_prop = {}
        for i in range(num_AO):
            do_prop['flag{:01d}'.format(i)] = {}
        self.create_digital_outputs(do_prop)
        _, _, do_widgets = self.auto_create_widgets()
        self.auto_place_widgets(('Digital Outputs/Flags', do_widgets))

        #Store the board number to be used:
        connection_object = self.settings['connection_table'].find_by_name(self.device_name)
        self.board_number = int(connection_object.BLACS_connection)
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
        
