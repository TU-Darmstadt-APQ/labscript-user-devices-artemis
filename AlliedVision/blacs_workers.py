import numpy as np
from labscript_utils import dedent
import threading
import labscript_utils.h5_lock
import h5py
from user_devices.logger_config import logger
from zprocess import rich_print

from blacs.tab_base_classes import Worker
import labscript_utils.properties
import zmq

from labscript_utils.ls_zprocess import Context
from labscript_utils.shared_drive import path_to_local
from labscript_utils.properties import set_attributes

# import vmbpy
# from vmbpy import VmbCameraError

vmbpy = None
VmbCameraError = None

class AlliedVisionCameraWrapper(object):
    def __init__(self, camera_id):
        self._import_python_libraries()

        self._abort_acquisition = False
        self.vmb = None
        self.cam = None

        self.vmb = vmbpy.VmbSystem.get_instance().__enter__()
        if camera_id:
            try:
                self.cam = self.vmb.get_camera_by_id(camera_id)
            except VmbCameraError:
                raise RuntimeError("Cound not find camera with id " + camera_id)
            except Exception:
                raise

        else:
            cams = self.vmb.get_all_cameras()
            if not cams:
                raise RuntimeError("No camera accessible.")
            for cam in cams:
                print(f"Found {str(cam.get_id())}")
            self.cam = cams[0]

        self.cam = self.cam.__enter__()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.cam is not None:
            self.cam.__exit__(exc_type, exc_value, exc_traceback)
        if self.vmb is not None:
            self.vmb.__exit__(exc_type, exc_value, exc_traceback)

    def _import_python_libraries(self):
        global vmbpy
        try:
            import vmbpy
            from vmbpy import VmbCameraError

        except ImportError as e:
            raise ImportError(
                "vmbpy not installed on this system"
            ) from e

        vmbpy = vmbpy

    def set_exposure_time(self, t):
        t = t * 1e6 # s -> us # fixme
        min_t, max_t = self.cam.ExposureTime.get_range()
        t = min(max_t, max(min_t, t))  # check bounds
        self.cam.ExposureTime.set(t)

    def set_gain(self, g):
        min_g, max_g = self.cam.Gain.get_range()
        g = min(max_g, max(min_g, g))  # check bounds
        self.cam.Gain.set(g)

    def snap(self, timeout):
        frame = self.cam.get_frame(timeout_ms=timeout*1e3)
        return self.process_frame(frame)

    def process_frame(self, frame):
        frame = frame.as_numpy_ndarray()
        H, W, C = frame.shape
        if C == 1:
            return frame.reshape(H, W)
        else:
            return frame

    def limit_fps(self, framerate):
        self.cam.AcquisitionFrameRateEnable.set(True)
        min_f, max_f = self.cam.AcquisitionFrameRate.get_range()
        framerate = min(max_f, max(min_f, framerate))  # check bounds
        self.cam.AcquisitionFrameRate.set(framerate)

    def unlimited_fps(self):
        if self.cam.AcquisitionFrameRateEnable.get():
            self.cam.AcquisitionFrameRateEnable.set(False)

    def configure_acquisition(self, frame_handler, buffer_count=10):
        # todo: allocation modes?
        # AllocationMode.AnnounceFrame -- buffer allocated by vmbpy
        # AllocationMode.AllocAndAnnounceFrame -- buffer allocated by the Transport Layer
        def internal_frame_handler(cam, stream, frame):
            f = self.process_frame(frame)
            cam.queue_frame(frame)
            frame_handler(f)

        self.cam.start_streaming(handler=internal_frame_handler, buffer_count=buffer_count)

    def stop_acquisition(self):
        self.cam.stop_streaming()

    def software_trigger(self):
        self.cam.TriggerSelector.set("FrameStart")
        self.cam.TriggerSource.set(f"Software")
        self.cam.AcquisitionMode.set(f"Continuous")
        if str(self.cam.TriggerMode.get()) == "On":
            self.cam.TriggerMode.set("Off")

    def hardware_trigger(self, gpio, activation):

        self.cam.LineSelector.set(f"Line{gpio}")
        self.cam.LineMode.set("Input")

        self.cam.TriggerSelector.set("FrameStart")
        gpio = min(3, max(0, gpio))
        self.cam.TriggerSource.set(f"Line{gpio}")
        self.cam.TriggerMode.set("On")
        self.cam.TriggerActivation.set(activation)

    def get_attributes_names(self, visibility_level, writable_only):
        """
        :param visibility_level: Beginner | Expert | Guru | Invisible
        :param writable_only: (bool)
        :return: list of all attribute names of readable attributes for the given visibility level. Optionally, only writable attributes.
        """
        names = []
        for feature in self.cam.get_all_features():
            if feature.get_visibility() == visibility_level:
                if writable_only and not feature.is_writable():
                    continue
                if not feature.is_readable():
                    continue
                names.append(feature.get_name())
        return names

    def get_attribute(self, name):
        feature = self.cam.get_feature_by_name(name)
        return feature.get()

    def set_attributes(self, attributes):
        for k, v in attributes.items():
            if k == "gain":
                self.set_gain(v)
            if k == "exposure_time":
                self.set_exposure_time(v)
            if k == "frame_rate":
                if v == 0: self.unlimited_fps()
                else: self.limit_fps(framerate=v)
            else:
                try:
                    feature = self.cam.get_feature_by_name(k)
                    feature.set(v)
                except Exception as e:
                    rich_print(f"Failed to set attribute {k}={v}: {e}", color=ORANGE)

class AlliedVisionCameraWorker(Worker):
    interface_class = AlliedVisionCameraWrapper

    def init(self):
        self.camera = self.get_camera()

        # Setting attributes
        self.camera.set_gain(self.manual_mode_gain)
        self.camera.set_exposure_time(self.manual_mode_exposure_time)

        self.images = None
        self.n_images = None
        self.exposures = None
        self.h5_filepath = None
        self.continuous_enabled = False
        self.smart_cache = {}
        self.exception_on_failed_shot = False
        self.attributes_to_save = None

        self.image_socket = Context().socket(zmq.REQ)
        self.image_socket.connect(f'tcp://{self.parent_host}:{self.image_reciever_port}')

    def get_camera(self):
        return self.interface_class(self.camera_id)

    def shutdown(self):
        pass

    def snap(self):
        """Acquire one frame in manual mode through software trigger."""
        self.camera.software_trigger()
        image = self.camera.snap(self.stop_acquisition_timeout)
        self._send_image_to_parent(image)

    def _send_image_to_parent(self, image):
        metadata = dict(dtype=str(image.dtype), shape=image.shape)
        self.image_socket.send_json(metadata, zmq.SNDMORE)
        self.image_socket.send(image, copy=False)
        response = self.image_socket.recv()
        assert response == b'ok', response

    def continuous_get_frame(self, frame):
        self._send_image_to_parent(frame)

    def buffered_get_frame(self, frame):
        self.images.append(frame)
        self._send_image_to_parent(frame)

    def start_continuous(self):
        assert not self.continuous_enabled

        self.camera.software_trigger()
        self.camera.set_gain(self.manual_mode_gain)
        self.camera.set_exposure_time(self.manual_mode_exposure_time)
        self.camera.limit_fps(10)
        self.camera.configure_acquisition(frame_handler=self.continuous_get_frame)
        self.continuous_enabled = True

    def stop_continuous(self, pause=False):
        self.camera.stop_acquisition()
        if not pause:
            self.continuous_enabled = False

    def program_manual(self, front_panel_values):
        return front_panel_values

    def check_remote_values(self):
        pass

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        rich_print("------------- Transition to Buffered ----------------", color=BLUE)
        if getattr(self, 'is_remote', False):
            h5_file = path_to_local(h5_file)

        if self.continuous_enabled:
            # Pause continuous acquisition during transition_to_buffered:
            self.stop_continuous(pause=True)

        with h5py.File(h5_file, 'r') as f:
            group = f['devices'][self.device_name]
            if not 'EXPOSURES' in group:
                return {}
            self.h5_filepath = h5_file
            self.exposures = group['EXPOSURES'][:]
            self.n_images = len(self.exposures)

            # Get the camera_attributes from the device_properties
            properties = labscript_utils.properties.get(
                f, self.device_name, 'device_properties'
            )
            self.exception_on_failed_shot = properties['exception_on_failed_shot']
            saved_attr_level = properties['saved_attribute_visibility_level']
            self.camera.exception_on_failed_shot = self.exception_on_failed_shot
            camera_attributes = {"gain": properties['gain'],
                                 "exposure_time": properties['exposure_time'],
                                 "framerate": properties['framerate']
                                 } # can be extended I guess ??????????????

        if self.n_images == 0: # no images in this shot
            return {}

        print(f"Configuring camera for {self.n_images} images.")

        self.camera.hardware_trigger(self.trigger_gpio)
        if fresh:
            self.smart_cache = {}
        self.set_attributes_smart(camera_attributes)

        self.images = []

        self.camera.configure_acquisition(frame_handler=self.buffered_get_frame, buffer_count=self.n_images)

        return {}

    def set_attributes_smart(self, camera_attributes):
        uncached_attributes = {}
        for name, value in camera_attributes.items():
            if name not in self.smart_cache or self.smart_cache[name] != value:
                uncached_attributes[name] = value
                self.smart_cache[name] = value
        self.camera.set_attributes(uncached_attributes)

    def transition_to_manual(self):
        rich_print("------------- Transition to Manual ----------------", color=BLUE)
        if self.h5_filepath is None:
            print('No camera exposures in this shot.\n')
            return True

        print("Stopping acquisition.")
        self.camera.stop_acquisition()

        print(f"Saving {len(self.images)}/{len(self.exposures)} images.")

        with h5py.File(self.h5_filepath, 'r+') as f:
            # Use orientation for image path, device_name if orientation unspecified
            if self.orientation is not None:
                image_path = 'images/' + self.orientation
            else:
                image_path = 'images/' + self.device_name
            image_group = f.require_group(image_path)
            image_group.attrs['camera'] = self.device_name

            # Whether we failed to get all the expected exposures:
            image_group.attrs['failed_shot'] = len(self.images) != len(self.exposures)

            # key the images by name and frametype. Allow for the case of there being
            # multiple images with the same name and frametype. In this case we will
            # save an array of images in a single dataset.
            images = {
                (exposure['name'], exposure['frametype']): []
                for exposure in self.exposures
            }

            # Iterate over expected exposures, sorted by acquisition time, to match them
            # up with the acquired images:
            self.exposures.sort(order='t')
            for image, exposure in zip(self.images, self.exposures):
                images[(exposure['name'], exposure['frametype'])].append(image)

            # Save images to the HDF5 file:
            for (name, frametype), imagelist in images.items():
                data = imagelist[0] if len(imagelist) == 1 else np.array(imagelist)
                print(f"Saving frame(s) {name}/{frametype}.")
                group = image_group.require_group(name)
                dset = group.create_dataset(
                    frametype, data=data, dtype='uint16', compression='gzip'
                )
                # Specify this dataset should be viewed as an image
                dset.attrs['CLASS'] = np.bytes_('IMAGE')
                dset.attrs['IMAGE_VERSION'] = np.bytes_('1.2')
                dset.attrs['IMAGE_SUBCLASS'] = np.bytes_('IMAGE_GRAYSCALE')
                dset.attrs['IMAGE_WHITE_IS_ZERO'] = np.uint8(0)

            try:
                image_block = np.stack(self.images)
                self._send_image_to_parent(image_block)
            except ValueError as e:
                print("Cannot display images from buffered. They are not the same shape." + e)


            # Save camera attributes to HDF5
            if self.visibility_level:
                self.attributes_to_save = self.get_attributes_as_dict(self.visibilty_level, writable_only=self.writable_only)
                print(f"[DEBUG] Attributes to save: ", self.attributes_to_save)
                set_attributes(group, self.attributes_to_save)


        self.images = None
        self.n_images = None
        self.exposures = None
        self.h5_filepath = None

        if self.continuous_enabled:
            # If continuous manual mode acquisition was in progress before the buffered run, resume it:
            self.start_continuous()
        return True

    def get_attributes_to_dict(self, visibility_level, writable_only):
        names = self.camera.get_attributes_names(visibility_level, writable_only)
        attributes_dict = {name: self.camera.get_attribute(name) for name in names}
        return attributes_dict

    def abort_transition_to_buffered(self):
        self.camera.stop_acquisition()
        self.images = None
        self.n_images = None
        self.exposures = None
        self.h5_filepath = None

        return True

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

# --------------------contants
BLUE = '#66D9EF'
GREEN = '#008000'
ORANGE = '#FFA500'
YELLOW = '#F5E727'
RED = '#F52727'