from blacs.tab_base_classes import Worker
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger
from blacs.tab_base_classes import MODE_MANUAL

class PicoScopeTab(DeviceTab):
    def initialise_GUI(self):
        return

    def initialise_workers(self):
        # Get properties from connection table.
        device = self.settings['connection_table'].find_by_name(self.device_name)

        # look up the serial number
        serial = device.properties["serial_number"]

        # Start a worker process
        self.create_worker(
            'main_worker',
            'user_devices.PicoScope4000A.BLACS_workers.PicoScopeWorker',
            {"serial_number": serial}  # All connection table properties should be added
        )
        self.primary_worker = "main_worker"