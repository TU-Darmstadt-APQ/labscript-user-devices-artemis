from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from blacs.tab_base_classes import MODE_MANUAL
import labscript_utils
from labscript_devices.IMAQdxCamera.blacs_tabs import IMAQdxCameraTab
from labscript_utils.ls_zprocess import ZMQServer
import h5py

class IDSCameraTab(IMAQdxCameraTab):
    worker_class = "user_devices.IDS_UI_5240SE.blacs_workers.IDSWorker"

    def initialise_workers(self):
        table = self.settings['connection_table']
        connection_table_properties = table.find_by_name(self.device_name).properties
        # The device properties can vary on a shot-by-shot basis, but at startup we will
        # initially set the values that are configured in the connection table, so they
        # can be used for manual mode acquisition:
        with h5py.File(table.filepath, 'r') as f:
            device_properties = labscript_utils.properties.get(
                f, self.device_name, "device_properties"
            )
        worker_initialisation_kwargs = {
            'serial_number': connection_table_properties['serial_number'],
            'camera_attributes': device_properties['camera_attributes'],
            'image_receiver_port': self.image_receiver.port,
        }
        self.create_worker(
            'main_worker', self.worker_class, worker_initialisation_kwargs
        )
        self.primary_worker = "main_worker"

