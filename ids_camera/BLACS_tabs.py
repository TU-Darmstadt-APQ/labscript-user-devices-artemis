from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger
from blacs.tab_base_classes import MODE_MANUAL

class CameraTab(DeviceTab):
    def initialise_GUI(self):

        self.supports_smart_programming(False)        
        self.supports_remote_value_check(False)
    
    def initialise_workers(self):

        worker_kwargs = {}
        self.create_worker(
            'main_worker',
            'user_devices.???.BLACS_workers.???',
            worker_kwargs,
            )
        
        self.primary_worker = "main_worker"
