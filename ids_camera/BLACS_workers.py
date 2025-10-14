import queue
import threading
import time

from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import h5py
from zprocess import rich_print
from user_devices.logger_config import logger

from .camera import Camera, TriggerWorker
from ids_peak import ids_peak
from qtutils.qt.QtGui import QImage
from datetime import datetime as dt
import numpy as np

import zmq
import labscript_utils
from labscript_utils.ls_zprocess import Context
from labscript_utils.shared_drive import path_to_local
import json


class CameraWorker(Worker):
    def init(self):
        # Socket for Worker-Tab communication
        self.image_socket = Context().socket(zmq.REQ)
        self.image_socket.connect(
            f'tcp://{self.parent_host}:{self.image_receiver_port}'
        )

        # Connecting to camera
        ids_peak.Library.Initialize()
        device_manager = ids_peak.DeviceManager.Instance()
        self.camera = Camera(device_manager, self.serial_number) # sets default cam setting

        # Configure triggering
        self.camera.init_hardware_trigger()
        self.trigger_mode = "Hardware"

        # Configure camera parameters
        self.set_4_parameters()

        # Start acquisition and worker waiting for trigger signal
        self.image_queue = queue.Queue()
        self.camera._init_data_stream()
        self.worker = TriggerWorker(self.camera._device, self.camera.node_map, self.camera._datastream, self.image_queue, keep_image=True)

        self.hardware_trigger_conf()
        self.start_acquisition()
        self.worker.start()

    def set_auto(self):
        self.camera.set_auto()


    def set_4_parameters(self):
        print(f"[DEBUG] 4 Parameters: (roi, gain, frame_rate, exp_time) = ({self.roi, self.gain, self.frame_rate, self.exposure_time})")
        if self.roi is not None and self.roi.size == 4:
            x, y, width, height = self.roi  # np.ndarray unpacking
            self.set_roi((int(x), int(y), int(width), int(height)))

        if self.gain is not None:
            self.set_gain(float(self.gain))

        if self.frame_rate is not None:
            self.set_fps(float(self.frame_rate))

        if self.exposure_time is not None:
            self.set_exposure(float(self.exposure_time))

    def _send_to_gui(self, image):
        """Send the image to the GUI to display. This will block if the parent process
        is lagging behind in displaying frames, in order to avoid a backlog.
        :param image (nparray)"""
        metadata = dict(dtype=str(image.dtype), shape=image.shape)
        self.image_socket.send_json(metadata, zmq.SNDMORE)
        self.image_socket.send(image, copy=False)
        response = self.image_socket.recv()
        assert response == b'ok', response

    def _save_to_hdf(self, hdf5_file, image, metadata):
        """
           Saves numpy-array of image and metadata under Device group in HDF5

           :param hdf5_file: hdf5 file
           :param image: numpy.ndarray
           :param metadata:  {'date': '2025-08-07', 'time': '12:00:00', 'description': 'manual shot'}
           """
        name = f'{metadata["date"]}_{metadata["time"].replace(":", "-")}'
        group = hdf5_file['devices'][self.device_name]
        group.attrs['camera'] = self.device_name

        dataset = group.create_dataset(name, data=image, compression='gzip')

        for key, value in metadata.items():
            dataset.attrs[key] = value

        print(f"Saved image with metadata in HDF5 under /devices/CameraIds/{name}")

    def shutdown(self):
        if self.camera is not None:
            self.camera.close()
        self.worker.stop()
        self.worker.join()
        ids_peak.Library.Close()

    def program_manual(self, front_panel_values):
        rich_print(f"---------- Manual MODE start: ----------", color=BLUE)
        print(f"front panel values: {front_panel_values}")
        return front_panel_values

    def check_remote_values(self):
        pass

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.h5_filepath = h5_file
        rich_print(f"---------- End transition to Buffered: ----------", color=BLUE)
        return

    def transition_to_manual(self):
        return True

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

    def software_trigger_snap(self, description=None):
        """ Take a software triggered snap:
        2. Trigger
        3. Save image to hdf5
        4. Display image on Tab

        Precondition: Camera configured on software triggering
        """
        if self.trigger_mode == "Software":
            # Software Trigger
            self.camera.software_trigger()

            # Grab image from TriggerWorker
            try:
                ipl_image = self.worker.image_queue.get(timeout=10)
            except queue.Empty:
                print("Timeout waiting for image from worker!")
                return

            np_array = self.camera.ipl2numpy(ipl_image)
            metadata = {
                'date': dt.now().strftime('%Y-%m-%d'),
                'time': dt.now().strftime('%H:%M:%S'),
                'description': 'manual snapshot'
            }

            if self.h5_filepath is None:
                raise LabscriptError(
                    "Cannot save image in h5file: "
                    "`self.h5_file` is not set. Make sure `transition_to_buffered()` has been called before sending to the device."
                )

            with h5py.File(self.h5_filepath, 'r+') as f:
                self._save_to_hdf(f, np_array, metadata)

            # Pass image to GUI
            self._send_to_gui(np_array)

        else:
            print(f"Device is currently configured with trigger mode = {self.trigger_mode}. "
                "Switch to software trigger before continuing.")

    def image2qt_image(self, image) -> QImage:
        image_numpy = image.get_numpy_1D().copy()
        qt_image = QtGui.QImage(image_numpy,
                                image.Width(), image.Height(),
                                QtGui.QImage.Format_RGB32)
        return qt_image

    def software_trigger_conf(self):
        self.camera.init_software_trigger()
        self.trigger_mode = "Software"
        self.worker.keep_image = True

    def hardware_trigger_conf(self):
        self.camera.init_hardware_trigger()
        self.trigger_mode = "Hardware"
        self.worker.keep_image = True

    def freerun_conf(self, value):
        frame_rate = value[0]
        self.worker.keep_image = False
        self.camera.init_freerun(frame_rate)
        print(f"Configure to freerun")
        self.trigger_mode = "Freerun"


    def start_freerun_acquisition(self):
        self.start_acquisition()
        self.worker.keep_image = False
        def freerun_thread():
            while self.camera.acquisition_running:
                # Grab image from TriggerWorker
                try:
                    self.worker.keep_image = False
                    ipl_image = self.worker.image_queue.get(timeout=2)
                    # Pass image to GUI
                    np_array = self.camera.ipl2numpy(ipl_image)
                    self._send_to_gui(np_array)
                except queue.Empty:
                    print("Timeout waiting for image from worker!")
                    return
        self.freerun = threading.Thread(target=freerun_thread, daemon=True)
        self.freerun.start()

    def set_fps(self, frame_rate):
        if isinstance(frame_rate, list) or isinstance(frame_rate, np.ndarray):
            fps = frame_rate[0]
        else:
            fps = frame_rate
        self.camera.set_frame_rate(fps)

    def set_exposure(self, exposure):
        if isinstance(exposure, list) or isinstance(exposure, np.ndarray):
            exp = exposure[0]
        else:
            exp = exposure
        self.camera.set_exposure_time(exp)

    def set_gain(self, gain):
        if isinstance(gain, list) or isinstance(gain, np.ndarray):
            g = gain[0]
        else:
            g = gain
        self.camera.set_gain(g)

    def set_roi(self, roi):
        x, y, w, h = roi
        self.camera.set_roi(x, y, w, h)

    def start_acquisition(self):
        self.camera.start_acquisition()

    def stop_acquisition(self):
        self.camera.stop_acquisition()


# --------------------contants
BLUE = '#66D9EF'