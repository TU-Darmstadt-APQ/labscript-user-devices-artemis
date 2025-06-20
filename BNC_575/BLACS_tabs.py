from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger

class BNC_575Tab(DeviceTab):
    def initialise_GUI(self):
        do_prop = {}
        for i in range(1, 9): # fixme
            do_prop['flag{:01d}'.format(i)] = {}
        self.create_digital_outputs(do_prop)
        _, _, do_widgets = self.auto_create_widgets()
        self.auto_place_widgets(('Digital Outputs/Flags', do_widgets))
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)

    def initialise_workers(self):
        connection_table = self.settings['connection_table']
        properties = connection_table.find_by_name(self.device_name).properties
        worker_property_keys = [
            "port", "baud_rate", "pulse_width", "trigger_mode",
            "t0_mode", "t0_period", "t0_burst_count",
            "t0_on_count", "t0_off_count", "trigger_logic", "trigger_level"
        ]

        worker_kwargs = {
            "name": self.device_name + '_main',
            **{k: properties[k] for k in worker_property_keys if k in properties}
        }
        
        self.create_worker(
            'main_worker',
            'user_devices.BNC_575.BLACS_workers.BNC_575Worker',
            worker_kwargs,
            )
        
        self.primary_worker = "main_worker"