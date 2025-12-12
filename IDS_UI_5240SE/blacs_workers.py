from blacs.tab_base_classes import Worker
import threading
import numpy as np
from labscript_utils import dedent
import labscript_utils.h5_lock
import h5py
import labscript_utils.properties
from zprocess import rich_print
import zmq
import time
from labscript import LabscriptError

from labscript_utils.ls_zprocess import Context
from labscript_utils.shared_drive import path_to_local
from labscript_utils.properties import set_attributes
from labscript_devices.IMAQdxCamera.blacs_workers import IMAQdxCameraWorker

from ids_peak import ids_peak
from ids_peak_ipl import ids_peak_ipl
from ids_peak import ids_peak_ipl_extension
from datetime import datetime as dt

import os

BLUE = '#66D9EF'
RED = '#FF6347'
YELLOW = '#E6DB74'
GREEN = '#A6E22E'

class IDS_Camera(object):
    def __init__(self, serial_number=None):
        # Initialize the library
        ids_peak.Library.Initialize()
        self.device_manager = ids_peak.DeviceManager.Instance()
        self.device_manager.Update()         # Update device manager to make sure every available device is listed

        # Find the camera
        self.camera = None

        if self.device_manager.Devices().empty():
            raise LabscriptError(f"Failed to open camera {serial_number}. No camera found.")

        # Open the camera
        if serial_number:
            for i, device in enumerate(self.device_manager.Devices()):
                # Display device information
                print(
                    f"{str(i)}:  {device.ModelName()} ("
                    f"{device.ParentInterface().DisplayName()} ; "
                    f"{device.ParentInterface().ParentSystem().DisplayName()} v."
                    f"{device.ParentInterface().ParentSystem().Version()} ;"
                    f"ser={device.SerialNumber()})")

                if int(device.SerialNumber()) == int(serial_number):
                    print(f"Open the camera with serial number {serial_number}")

                    timeout = 5 # 5 seconds
                    start = time.time()
                    while time.time() < start + timeout:
                        try:
                            self.camera = self.device_manager.Devices()[i].OpenDevice(ids_peak.DeviceAccessType_Control)
                        except ids_peak.BadAccessException:
                            time.sleep(1)

        # Open the first available device
        if self.camera is None:
            print(f"Camera with serial number {serial_number} not found. Open the first available camera. ")
            self.camera = self.device_manager.Devices()[0].OpenDevice(ids_peak.DeviceAccessType_Control)

        # Get device's control nodes
        self.node_map = self.camera.RemoteDevice().NodeMaps()[0]

        self._acquisition_running = False
        self.stop_event = threading.Event()
        self.trigger_mode = None

        self._datastream = None
        self._buffer_list = []

        self._image_converter = ids_peak_ipl.ImageConverter()
        self._image_transformer = ids_peak_ipl.ImageTransformer()
        self.all_collected = threading.Event()

        self.exception_on_failed_shot = True

    def set_attributes(self, attr_dict):
        for k, v in attr_dict.items():
            self.set_attribute(k, v)

    def _check_bounds(self, name: str, value:float, min_val:float, max_val:float, increment:float=None):
        if not (min_val <= value <= max_val):
            raise LabscriptError(f"{name} value={value} out of range [{min_val}, {max_val}]")
        # if increment and (value % increment != 0):
        #     raise LabscriptError(f"{name} value={value} not aligned to increment {increment}")

    def set_attribute(self, name, value):
        """Set the value of the attribute of the given name to the given value"""
        _value = value  # Keep the original for the sake of the error message
        try:
            if name == 'exposure_time_ms':
                self.set_exposure_time(value * 1e+6) # s -> us
            if name == 'gain':
                self.set_gain(value)
            if name == 'roi':
                x, y, width, height = value
                self.set_roi(x, y, width, height)
            if name == 'frame_rate_fps':
                self.set_frame_rate(value)

        except Exception as e:
            # Add some info to the exception:
            msg = f"failed to set attribute {name} to {value}"
            raise Exception(msg) from e

    def set_exposure_time(self, exposure_time_us:int):
        """Sets the camera exposure time in microseconds.
        Precondition: The IDS peak API is initialized and a camera is opened.
        """
        try:
            node = self.node_map.FindNode("ExposureTime")
            min_time = node.Minimum()
            max_time = node.Maximum()
            current_time = node.Value()
            # Set exposure time
            self._check_bounds("Exposure", current_time, min_time, max_time)
            node.SetValue(exposure_time_us)
            print(f"\t Exposure time changed: {current_time} µs --> {exposure_time_us} µs")
        except Exception as e:
            raise Exception(f"Failed to set exposure time: {e}")

    def set_gain(self, gain:float):
        """Master gain to all channels. The gains may be achieved by combining analog and digital gain."""
        try:
            gain_node = self.node_map.FindNode("Gain")
            self.node_map.FindNode("GainSelector").SetCurrentEntry("All")

            min_gain = gain_node.Minimum()
            max_gain = gain_node.Maximum()
            inc_gain = gain_node.Increment() if gain_node.HasConstantIncrement() else None
            current_gain = gain_node.Value()

            self._check_bounds("Gain", gain, min_gain, max_gain, inc_gain)
            gain_node.SetValue(gain)
            print(f"\t Gain changed: {current_gain} --> {gain}")

        except Exception as e:
            raise Exception(f"Failed to set gain: {e}")

    def set_roi(self, x, y, width, height):
        try:
            was_running = False
            if self._acquisition_running:  # Stop acquisition and revoke all buffers
                self.stop_acquisition()
                was_running = True

            offset_x_node = self.node_map.FindNode("OffsetX")
            offset_y_node = self.node_map.FindNode("OffsetY")
            width_node = self.node_map.FindNode("Width")
            height_node = self.node_map.FindNode("Height")

            # Get the minimum ROI and set it. After that there are no size restrictions anymore
            x_min = offset_x_node.Minimum()
            y_min = offset_y_node.Minimum()
            w_min = width_node.Minimum()
            h_min = height_node.Minimum()

            offset_x_node.SetValue(x_min)
            offset_y_node.SetValue(y_min)
            width_node.SetValue(w_min)
            height_node.SetValue(h_min)

            # Get bounds and increments
            x_max, x_inc = offset_x_node.Maximum(), offset_x_node.Increment()
            y_max, y_inc = offset_y_node.Maximum(), offset_y_node.Increment()
            w_max, w_inc = width_node.Maximum(), width_node.Increment()
            h_max, h_inc = height_node.Maximum(), height_node.Increment()

            if width % w_inc != 0:
                corrected = (width // w_inc) * w_inc
                print(f"[ROI] Adjust width {width} → {corrected} (step {w_inc})")
                width = corrected

            if height % h_inc != 0:
                corrected = (height // h_inc) * h_inc
                print(f"[ROI] Adjust height {height} → {corrected} (step {h_inc})")
                height = corrected

            if x % x_inc != 0:
                corrected = (x // x_inc) * x_inc
                print(f"[ROI] Adjust width {x} → {corrected} (step {x_inc})")
                x = corrected

            if y % y_inc != 0:
                corrected = (y // y_inc) * y_inc
                print(f"[ROI] Adjust height {y} → {corrected} (step {y_inc})")
                y = corrected

            if (x + width > w_max) or (y + height > h_max):
                raise LabscriptError(
                    f"ROI: (x+width={x + width}, y+height={y + height}) exceeds limits ({w_max},{h_max}).")
            if (width % w_inc != 0) or (height % h_inc != 0):
                raise LabscriptError(
                    f"ROI: width or/and height ({width}, {height}) not aligned to increments ({w_inc},{h_inc})")
            self._check_bounds("OffsetX", x, x_min, x_max, x_inc)
            self._check_bounds("OffsetY", y, y_min, y_max, y_inc)

            # Set new values
            offset_x_node.SetValue(x)
            offset_y_node.SetValue(y)
            width_node.SetValue(width)
            height_node.SetValue(height)

            # Allocate new buffers and start acquisition if was running
            if was_running:
                self.configure_acquisition()
                self.start_acquisition()

            print(f"\t ROI changed --> {x, y, width, height}.")

        except Exception as e:
            raise LabscriptError(f"Failed to set ROI: {e}.")

    def set_frame_rate(self, frame_rate):
        try:
            frame_rate_node = self.node_map.FindNode("AcquisitionFrameRate")
            min_rate = frame_rate_node.Minimum()
            max_rate = frame_rate_node.Maximum()
            # inc_rate = frame_rate_node.Increment() if frame_rate_node.HasConstantIncrement() else None
            current_rate = frame_rate_node.Value()

            self._check_bounds("Frame rate", frame_rate, min_rate, max_rate)
            frame_rate_node.SetValue(frame_rate)

            print(f"\t Frame rate changed: {current_rate} --> {frame_rate}")

        except Exception as e:
            print(f"Failed to set frame rate: {e}")

    def get_attribute(self, name):
        """Return current value of attribute of the given name"""
        try:
            node = self.node_map.FindNode(name)
            if isinstance(node, ids_peak.FloatNode) or isinstance(node, ids_peak.IntegerNode):
                value = str(node.Value()) + node.Unit()
            elif isinstance(node, ids_peak.CategoryNode):
                value = [sub_node.Name() for sub_node in node.SubNodes()]
            elif isinstance(node, ids_peak.EnumerationNode):
                value = node.CurrentEntry().SymbolicValue()
            elif isinstance(node, ids_peak.CommandNode):
                value = "is_done=" + str(node.IsDone())
            elif isinstance(node, ids_peak.Node):
                value = {
                    "name": node.Name(),
                    "display_name": node.DisplayName(),
                    "type": node.Type()
                }
            else:
                value = node.Value()
        except ids_peak.InternalErrorException as e:
            value = f"Cannot evaluate: {e}"
        except Exception as e:
            raise Exception(f"Failed to get attribute {name}. {e}")

        return value

    def get_attribute_names(self, visibility_level, writeable_only=True):
        """Return a list of all attribute names of readable attributes, for the given
               visibility level. Optionally return only writeable attributes"""
        attributes = []

        try:
            if writeable_only:
                for node in self.node_map.Nodes():
                    if node.Visibility() == visibility_level and node.IsWriteable():
                        attributes.append(node.Name())
            else:
                for node in self.node_map.Nodes():
                    if node.Visibility() == visibility_level and node.IsReadable() and not isinstance(node, ids_peak.Node):
                        attributes.append(node.Name())
        except Exception:
            raise

        return attributes

    def alloc_announce_buffers(self):
        """ Create minimum required amount of buffers to the stream."""
        payload_size = self.node_map.FindNode("PayloadSize").Value()
        buffer_amount = self._datastream.NumBuffersAnnouncedMinRequired()

        for _ in range(buffer_amount):
            buffer = self._datastream.AllocAndAnnounceBuffer(payload_size)
            self._buffer_list.append(buffer)

        # print(f"{buffer_amount} allocated & announced buffers!")

    def snap(self):
        """Execute Software Trigger. Only available in software trigger mode in MANUAL mode.
        Before the shot execution, acquisition is not started yet. So we start acquisition and pause it after the snapping."""
        if self.trigger_mode != 'software':
            self.configure_software_trigger_mode()

        stop_acquisition_flag = False
        if not self._acquisition_running:
            stop_acquisition_flag = True
            self.configure_acquisition()
            self.start_acquisition()

        self.node_map.FindNode("TriggerSoftware").Execute()
        self.node_map.FindNode("TriggerSoftware").WaitUntilDone()
        rich_print("!! Software trigger Executed !!", color=GREEN)

        timeout_ms = ids_peak.Timeout.INFINITE_TIMEOUT
        buffer = self._datastream.WaitForFinishedBuffer(timeout_ms)
        ipl_image = ids_peak_ipl_extension.BufferToImage(buffer)

        if stop_acquisition_flag:
            self.pause_acquisition()

        return ipl_image

    def grab(self, timeout_ms):
        np_image = None
        buffer = None
        while not self.stop_event.is_set():
            try:
                buffer = self._datastream.WaitForFinishedBuffer(timeout_ms)
            except ids_peak.TimeoutException:
                rich_print(f"[WARNING] Timeout exceeded while waiting for image", color=RED)
                continue
            except (ids_peak.InternalErrorException, ids_peak.IOException) as e:
                if self.exception_on_failed_shot:
                    raise

            if buffer is None:
                print("[DEBUG] No buffered data ...")
                continue

            # Image is transferred, get image from buffer and free the buffer
            np_image = ids_peak_ipl_extension.BufferToImage(buffer).get_numpy().copy()
            self._datastream.QueueBuffer(buffer)  # free buffer
            break

        return np_image

    def grab_multiple(self, images, n_images:int, timeout_ms=None):
        # print("[DEBUG] Acquiring frames from buffers .... ")
        self.all_collected.clear()

        for i in range(n_images):
            while True:
                if self.stop_event.is_set():
                    print("Abort during acquisition.")
                    return
                try:
                    np_image = self.grab(timeout_ms)
                except Exception as e:
                    rich_print(f"[ERROR] Exception while grabbing image {i + 1}: {e}", color=RED)
                    continue

                images.append(np_image)
                print(f"\nGot image {i + 1} of {n_images}.\n")
                break

        self.all_collected.set()
        self.stop_event.set()
        print("[INFO] Finished grabbing all images.")

    def configure_acquisition(self):
        """Flush queue, clear all old buffers if given, allocate and announce buffers"""
        # print("[DEBUG] Configuring acquisition ...")
        if self._acquisition_running:
            self.stop_acquisition()

        if self._datastream is None:        # Open datastream
            self._datastream = self.camera.DataStreams()[0].OpenDataStream()

        self.alloc_announce_buffers()

        # Queue Buffers
        for buffer in self._datastream.AnnouncedBuffers():
            self._datastream.QueueBuffer(buffer)

        self.stop_event.clear()

    def start_acquisition(self):
        print("[DEBUG] Starting acquisition ...")

        try:
            # Lock writeable nodes during acquisition
            self.node_map.FindNode("TLParamsLocked").SetValue(1)

            self._datastream.StartAcquisition()
            self.node_map.FindNode("AcquisitionStart").Execute()
            self.node_map.FindNode("AcquisitionStart").WaitUntilDone()
            self._acquisition_running = True

        except Exception as e:
            raise Exception(f"Exception (start acquisition): {str(e)}")

    def stop_acquisition(self):
        """ Stops the acquisition and discard all buffers"""
        if not self._acquisition_running:
            return

        try:
            self.node_map.FindNode("AcquisitionStop").Execute()
            self._datastream.StopAcquisition(ids_peak.AcquisitionStopMode_Default)
            # Discard all buffers from the acquisition engine, any associated queue
            # They remain in the announced buffer pool
            self._datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)
            for buffer in self._datastream.AnnouncedBuffers():
                # Remove buffer from the transport layer
                self._datastream.RevokeBuffer(buffer)
                self._buffer_list = []
            self._acquisition_running = False

            # Unlock parameters
            self.node_map.FindNode("TLParamsLocked").SetValue(0)

            self.stop_event.set()
        except Exception as e:
            raise LabscriptError(f"Failed to stop acquisition: {e}")

        print("[INFO] Acquisition is stopped. Buffers are discarded and revoked. ")


    def pause_acquisition(self):
        """Stops the acquisition, but buffers are discarded but still allocated and datastream are still opened.
        Intention: to start the acquisition again."""
        if not self._acquisition_running:
            return

        try:
            self.node_map.FindNode("AcquisitionStop").Execute()
            self._datastream.StopAcquisition(ids_peak.AcquisitionStopMode_Default)
            # Discard all buffers from the acquisition engine, any associated queue
            # They remain in the announced buffer pool
            self._datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)
            self._acquisition_running = False

            # Unlock parameters
            self.node_map.FindNode("TLParamsLocked").SetValue(0)
        except Exception as e:
            raise LabscriptError(f"Failed to pause acquisition: {e}")

        print("[INFO] Acquisition is paused. Buffers are discarded, but still announced ")

    def abort_acquisition(self):
        """Aborts the grabbing thread. """
        self.stop_event.set()

    def close(self):
        # fixme: worker timed out
        ids_peak.Library.Close()

    def configure_freerun_mode(self, frame_rate):
        print("[INFO] Configure FREERUN")
        self.node_map.FindNode("AcquisitionMode").SetCurrentEntry("Continuous")
        self.node_map.FindNode("TriggerSelector").SetCurrentEntry("ExposureStart")
        self.node_map.FindNode("TriggerMode").SetCurrentEntry("Off")

        self.node_map.FindNode("AcquisitionFrameRate").SetValue(float(frame_rate))

        self.trigger_mode = 'freerun'

    def configure_software_trigger_mode(self):
        print("[INFO] Configure SOFTWARE")
        self.node_map.FindNode("TriggerSelector").SetCurrentEntry("ExposureStart")
        self.node_map.FindNode("TriggerMode").SetCurrentEntry("On")
        self.node_map.FindNode("TriggerSource").SetCurrentEntry("Software")

        self.trigger_mode = 'software'

    def configure_hardware_trigger_mode(self, trigger_activation:str, delay:float):
        print("[INFO] Configure HARDWARE")
        self.node_map.FindNode("TriggerSelector").SetCurrentEntry("ExposureStart")
        self.node_map.FindNode("TriggerMode").SetCurrentEntry("On")
        self.node_map.FindNode("TriggerSource").SetCurrentEntry("Line0")
        self.node_map.FindNode("TriggerActivation").SetCurrentEntry(trigger_activation)
        self.node_map.FindNode("TriggerDelay").SetValue(delay)

        self.trigger_mode = 'hardware'


class IDSWorker(IMAQdxCameraWorker):
    interface_class = IDS_Camera

    def init(self):
        self.camera = self.get_camera()
        self.trigger_mode = 'software'
        self.camera.configure_software_trigger_mode()

        self.image_socket = Context().socket(zmq.REQ)
        self.image_socket.connect(
            f'tcp://{self.parent_host}:{self.image_receiver_port}'
        )

        self.attributes_to_save = None
        self.h5_filepath = None
        self.n_images = None
        self.smart_cache = {}
        self.images = None
        self.acquisition_thread = None
        self.continuous_thread = None
        self.acquisition_timeout = ids_peak.Timeout.INFINITE_TIMEOUT

    def get_camera(self):
        return self.interface_class(self.serial_number)

    def set_attributes_smart(self, attributes):
        """Call self.camera.set_attributes() to set the given attributes, only setting
        those that differ from their value in, or are absent from self.smart_cache.
        Update self.smart_cache with the newly-set values"""
        uncached_attributes = {}
        for name, value in attributes.items():
            if name not in self.smart_cache or self.smart_cache[name] != value:
                uncached_attributes[name] = value
                self.smart_cache[name] = value
        self.camera.set_attributes(uncached_attributes)

    def get_attributes_as_dict(self, visibility_level, writeable_only=None):
        """Return a dict of the attributes of the camera for the given visibility
        level"""
        names = self.camera.get_attribute_names(visibility_level, writeable_only)
        attributes_dict = {name: self.camera.get_attribute(name) for name in names}
        return attributes_dict

    def get_attributes_as_text(self, visibility_level):
        """Return a string representation of the attributes of the camera for
        the given visibility level. ['Simple', 'Intermediate', 'Advanced']"""
        visibility_level_mapping = {'Simple': 0,
                                    'Intermediate': 1,
                                    'Advanced': 2}
        attrs = self.get_attributes_as_dict(visibility_level_mapping[visibility_level], True)
        # Format it nicely:
        lines = [f'    {repr(key)}: {repr(value)},' for key, value in attrs.items()]
        dict_repr = '\n'.join(['{'] + lines + ['}'])
        return self.device_name + '_camera_attributes = ' + dict_repr

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        print(f" ------------------ Transition to Buffered --------------------")
        if self.continuous_thread is not None:
            self.stop_continuous(pause=True)

        # get number of frames to capture
        with h5py.File(h5_file, 'r') as f:
            group = f['devices'][self.device_name]
            if not 'EXPOSURES' in group:
                return {}
            self.exposures = group['EXPOSURES'][:]
            self.h5_filepath = h5_file
            self.n_images = len(self.exposures)

            # Get the camera_attributes from the device_properties
            properties = labscript_utils.properties.get(
                f, self.device_name, 'device_properties'
            )

        camera_attributes = properties['camera_attributes']
        self.visibility_level = properties['visibility']
        trigger_activation = properties['trigger_activation']
        trigger_delay = properties['trigger_delay'] * 1e+6 # s -> us
        self.exception_on_failed_shot = properties['exception_on_failed_shot']
        self.camera.exception_on_failed_shot = self.exception_on_failed_shot
        if properties['acquisition_timeout'] is None:
            self.acquisition_timeout = ids_peak.Timeout.INFINITE_TIMEOUT
        else:
            self.acquisition_timeout = ids_peak.Timeout(int(properties['acquisition_timeout'] * 1000))

        # print("[DEBUG] Properties: ", properties)

        # Only reprogram attributes that differ from those last programmed in, or all of
        # them if a fresh reprogramming was requested:
        if fresh:
            self.smart_cache = {}

        self.set_attributes_smart(camera_attributes)

        print(f"Configuring camera for {self.n_images} images with hardware trigger mode.")
        self.camera.configure_hardware_trigger_mode(trigger_activation, trigger_delay)
        self.camera.stop_event.clear()
        self.camera.configure_acquisition()
        self.camera.start_acquisition()
        self.images = []
        self.acquisition_thread = threading.Thread(
            target=self.camera.grab_multiple,
            args=(self.images, self.n_images, self.acquisition_timeout),
            daemon=True,
        )
        self.acquisition_thread.start()
        return {}

    def save_image(self, image, extension="png"):
        """ Saves image with given extension.
        :param image (ipl_image): image
        :param extension (str): png, jpg, bmp"""
        match extension:
            case "png":
                ids_peak_ipl.ImageWriter.WriteAsPNG(self.image_name(".png"), image)
            case "jpg":
                ids_peak_ipl.ImageWriter.WriteAsJPG(self.image_name(".jpg"), image)
            case "bmp":
                ids_peak_ipl.ImageWriter.WriteAsBMP(self.image_name(".bmp"), image)
        print("Image saved!")

    def image_name(self, ext: str) -> str:
        cwd = os.getcwd()
        path = cwd + "/labscript-suite/userlib/user_devices/IDS_UI_5240SE/images/" # todo: define your own dictionary here
        today_str = dt.now().strftime("%Y-%m-%d")
        pattern = f"{today_str}_"

        # count how many images with this data exist
        existing = [f for f in os.listdir(path) if f.startswith(pattern) and f.endswith(ext)]
        index = len(existing) + 1

        filename = f"{today_str}_{index}{ext}"
        full_path = os.path.join(path, filename)
        return full_path

    def _send_image_to_parent(self, image):
        """Send the image to the GUI to display. This will block if the parent process
        is lagging behind in displaying frames, in order to avoid a backlog."""
        metadata = dict(dtype=str(image.dtype), shape=image.shape)
        self.image_socket.send_json(metadata, zmq.SNDMORE)
        self.image_socket.send(image, copy=False)
        response = self.image_socket.recv()
        assert response == b'ok', response


    def transition_to_manual(self):
        print(f" ------------------ Transition to Manual --------------------")
        if self.h5_filepath is None:
            print('\n No camera exposures in this shot.\n')
            return True

        # wait till acquisition thread is closed
        self.camera.all_collected.wait()

        # stop acquisition
        self.camera.stop_acquisition()

        print(f"Saving {len(self.images)}/{self.n_images} images after shot.")
        # images/orientation|device_name/label=image/frametype
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

            names = self.exposures['name']
            frametypes = self.exposures['frametype']

            exposure_names = [n.decode() if isinstance(n, bytes) else n for n in names]
            frametypes = [f.decode() if isinstance(f, bytes) else f for f in frametypes]

            # Write each image as a separate dataset
            for idx, image in enumerate(self.images):
                group = image_group.require_group(exposure_names[idx])
                dset = group.create_dataset(frametypes[idx], data=image, compression='gzip')
                self._send_image_to_parent(image)

        try:
            image_block = np.stack(self.images)
        except ValueError:
            print("Cannot display images in the GUI, they are not all the same shape")
        else:
            self._send_image_to_parent(image_block)

        # Save camera attributes to the HDF5 file: fixme:
        if self.visibility_level is not None:
            self.attributes_to_save = self.get_attributes_as_dict(self.visibility_level, writeable_only=False)
            print("attributes to save !!!!!!!!!!!!!!!!!: ", self.attributes_to_save)
            set_attributes(image_group, self.attributes_to_save)


        self.images = None
        self.n_images = None
        self.attributes_to_save = None
        self.h5_filepath = None
        self.stop_acquisition_timeout = None
        self.exception_on_failed_shot = None

        return True

    def abort(self):
        if self.acquisition_thread is not None:
            if self.acquisition_thread.is_alive():
                rich_print("[WARNING] ABORTING: Acquisition thread did not finish. ", color=RED)
                self.camera.abort_acquisition()
            self.acquisition_thread.join()
            self.acquisition_thread = None
            self.camera.stop_acquisition()
        self.images = None
        self.n_images = None
        self.attributes_to_save = None
        self.exposures = None
        self.acquisition_thread = None
        self.h5_filepath = None
        self.stop_acquisition_timeout = None
        self.exception_on_failed_shot = None

        return True

    def abort_buffered(self):
        return self.abort()

    def abort_transition_to_buffered(self):
        return self.abort()

    def program_manual(self, values):
        return {}

    def shutdown(self):
        self.abort()
        if self.continuous_thread is not None:
            self.stop_continuous()
        self.camera.close()

    def snap(self):
        ipl_image = self.camera.snap()
        np_image = ipl_image.get_numpy()
        self._send_image_to_parent(np_image)
        self.save_image(ipl_image, 'png')

    def start_continuous(self, fps=10):
        if fps < 0.5:
            print("[INFO] FPS should be > 0.5")
            fps = 10
        print("Starting freerun with fps: ", fps)
        self.camera.configure_freerun_mode(fps)
        self.camera.configure_acquisition()
        self.camera.start_acquisition()
        self.continuous_thread = threading.Thread(target=self.continuous_loop, daemon=True)
        self.continuous_thread.start()

    def continuous_loop(self):
        while True:
            if self.camera.stop_event.is_set():
                break
            np_image = self.camera.grab(self.acquisition_timeout)
            self._send_image_to_parent(np_image)

        print("continuous_loop loop closed")

    def stop_continuous(self, pause=False):
        self.camera.stop_event.set()
        self.continuous_thread.join()
        self.continuous_thread = None

        if pause:
            self.camera.pause_acquisition()
        else:
            self.camera.stop_acquisition()




