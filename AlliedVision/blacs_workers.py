import cv2
from vmbpy import *

with VmbSystem.get_instance() as vmb:
    cams = vmb.get_all_cameras()
    with cams[0] as cam:
        frame = cam.get_frame()
        frame.convert_pixel_format(PixelFormat.Mono8)
        cv2.imwrite('frame.jpg', frame.as_opencv_image())



from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import h5py
from user_devices.logger_config import logger


class CameraWorker(Worker):
    def init(self):
        pass

    def shutdown(self):
        pass

    def program_manual(self, front_panel_values):
        return front_panel_values

    def check_remote_values(self):
        pass

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        return

    def transition_to_manual(self):
        return True

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

