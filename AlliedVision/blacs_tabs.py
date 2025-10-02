from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from blacs.tab_base_classes import MODE_MANUAL

from user_devices.logger_config import logger
import labscript_utils.properties
from labscript_utils.ls_zprocess import ZMQServer

class CameraTab(DeviceTab):
    def initialise_GUI(self):
        pass

    def initialise_workers(self):
        worker_kwargs = {}
        self.create_worker(
            'main_worker',
            'user_devices.ids_camera.blacs_workers.CameraWorker',
            worker_kwargs,
        )

        self.primary_worker = "main_worker"