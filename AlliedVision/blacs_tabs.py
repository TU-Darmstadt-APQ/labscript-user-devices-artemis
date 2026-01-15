from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from blacs.tab_base_classes import MODE_MANUAL
from user_devices.logger_config import logger
import labscript_utils.properties
from labscript_devices.IMAQdxCamera.blacs_tabs import IMAQdxCameraTab
import ast

import labscript_utils.h5_lock
import h5py

from blacs.tab_base_classes import define_state, MODE_MANUAL
from blacs.device_base_class import DeviceTab

import labscript_utils.properties
from labscript_utils.ls_zprocess import ZMQServer


class AlliedVisionCameraTab(IMAQdxCameraTab):
    # Subclasses may override this if all they do is replace the worker class with a
    # different one:
    worker_class = 'user_devices.AlliedVision.blacs_workers.AlliedVisionCameraWorker'

    def get_save_data(self):
        return {
            'acquiring': self.acquiring,
            'colormap': repr(self.image.ui.histogram.gradient.saveState())
        }

    def restore_save_data(self, save_data):
        if save_data.get('acquiring', False):
            # Begin acquisition
            self.on_continuous_clicked(None)
        if 'colormap' in save_data:
            self.image.ui.histogram.gradient.restoreState(
                ast.literal_eval(save_data['colormap'])
            )

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

        camera_attributes = {
            "exposure_time": device_properties['exposure_time'],
            "gain": device_properties['gain'],
            "framerate": device_properties['framerate'],
        }
        worker_initialisation_kwargs = {
            'camera_id': connection_table_properties['camera_id'],
            'orientation': connection_table_properties['orientation'],
            'camera_attributes': camera_attributes,
            'manual_mode_gain': connection_table_properties['manual_mode_gain'],
            'manual_mode_exposure_time': connection_table_properties['manual_mode_exposure_time'],
            'image_receiver_port': self.image_receiver.port,
            'trigger_gpio': connection_table_properties['trigger_gpio'],
            'stop_acquisition_timeout': device_properties['stop_acquisition_timeout']
        }
        self.create_worker(
            'main_worker', self.worker_class, worker_initialisation_kwargs
        )
        self.primary_worker = "main_worker"
