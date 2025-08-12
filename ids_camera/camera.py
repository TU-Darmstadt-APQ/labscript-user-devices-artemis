import time

from ids_peak import ids_peak
from ids_peak_ipl import ids_peak_ipl
from ids_peak import ids_peak_ipl_extension
from datetime import datetime as dt
import threading

import sys
import os
from os.path import exists
import h5py
import numpy as np

from user_devices.logger_config import logger


try:
    from labscript import LabscriptError as BaseCameraError
except ImportError:
    class BaseCameraError(Exception):
        """Fallback base error during development"""
        pass

class CameraError(BaseCameraError):
    """Custom camera error; will be LabscriptError in production"""
    def __init__(self, message):
        super().__init__(message)
        print(f"[CameraError] {message}")  # Optional console feedback

TARGET_PIXEL_FORMAT = ids_peak_ipl.PixelFormatName_BGRa8

class Camera:
    def __init__(self, device_manager, serial_number, interface=None):
        self.ipl_image = None
        self.device_manager = device_manager

        self._device = None
        self._datastream = None
        self.acquisition_running = False
        self.node_map = None
        self._interface = interface
        self.make_image = False
        self._buffer_list = []
        self.opened = False
        self.killed = False
        self.trigger_mode = None

        if serial_number is not None:
            self._get_device(serial_number)
        else:
            raise CameraError("Cannot find device. Set camera's serial number!")

        if self._interface is not None:
            self._interface.set_camera(self)

        self._image_converter = ids_peak_ipl.ImageConverter()
        self._image_transformer = ids_peak_ipl.ImageTransformer()

        # Continuous mode for triggering
        self.node_map.FindNode("AcquisitionMode").SetCurrentEntry("Continuous")

    def __del__(self):
        self.close()

    def close(self):
        self.stop_acquisition()

        # If datastream has been opened, revoke and deallocate all buffers
        try:
            self.revoke_buffers()
        except Exception as e:
            print(f"Exception (close): {str(e)}")

    def _get_device(self, serial_no:str):
        """Opens camera with specified serial number. Sets the default camera settings."""
        # Update device manager to make sure every available device is listed
        self.device_manager.Update()
        if self.device_manager.Devices().empty():
            print("No device found.")
            raise CameraError("No camera devices found.")

        # List all available devices
        selected_device_idx = None
        for i, device in enumerate(self.device_manager.Devices()):
            # Display device information
            print(
                f"{str(i)}:  {device.ModelName()} ("
                f"{device.ParentInterface().DisplayName()} ; "
                f"{device.ParentInterface().ParentSystem().DisplayName()} v."
                f"{device.ParentInterface().ParentSystem().Version()})")
            if device.SerialNumber() == serial_no:
                selected_device_idx = i

        if selected_device_idx is None:
            raise CameraError(f"Camera with serial number '{serial_no}' not found.")

        # Opens the selected device in control mode
        self._device = self.device_manager.Devices()[selected_device_idx].OpenDevice(ids_peak.DeviceAccessType_Control)
        self.opened = True

        # Get device's control nodes
        self.node_map = self._device.RemoteDevice().NodeMaps()[0]

        # Load the default/user settings
        self.load_user_set("Default")

        print("Finished opening device!")

    def _init_data_stream(self):
        try:
            # Open device's datastream
            self._datastream = self._device.DataStreams()[0].OpenDataStream()
            # Allocate image buffer for image acquisition
            self.alloc_buffers()
        except Exception as e:
            raise CameraError(f"Failed to open datastream: {e}.")

    def revoke_buffers(self):
        if self._datastream is None:
            return
        try:
            for buffer in self._datastream.AnnouncedBuffers():
                # Remove buffer from the transport layer
                self._datastream.RevokeBuffer(buffer)

            self._buffer_list = []
        except Exception as e:
            raise CameraError(f"Failed to revoke buffers: {e}")

    def alloc_buffers(self):
        """ Create minimum required amount of buffers to the stream."""
        # Buffer size
        payload_size = self.node_map.FindNode("PayloadSize").Value()

        # Minimum number of required buffers
        buffer_amount = self._datastream.NumBuffersAnnouncedMinRequired()

        # Allocate buffers and add them to the pool
        for _ in range(buffer_amount):
            # Let the TL allocate the buffers
            buffer = self._datastream.AllocAndAnnounceBuffer(payload_size)
            # Put the buffer in the pool
            self._datastream.QueueBuffer(buffer)
            # Add to the buffer list
            self._buffer_list.append(buffer)

        print(f"{buffer_amount} allocated buffers!")

    def start_acquisition(self):
        """Starts acquisition.
        1. initialize datastream --> Allocate buffers
        2. Preallocate conversion buffers (optional)
        3. Sets acquisition mode
        4. Starts Acquisition

        :return boolean
        """
        if self._device is None:
            return False
        if self.acquisition_running:
            return True
        if self._datastream is None:
            self._init_data_stream()

        try:
            # Lock writeable nodes during acquisition
            self.node_map.FindNode("TLParamsLocked").SetValue(1)

            image_width = self.node_map.FindNode("Width").Value()
            image_height = self.node_map.FindNode("Height").Value()
            input_pixel_format = ids_peak_ipl.PixelFormat(self.node_map.FindNode("PixelFormat").CurrentEntry().Value())

            # Pre-allocate conversion buffers to speed up first image conversion
            # while the acquisition is running
            # NOTE: Re-create the image converter, so old conversion buffers get freed
            self._image_converter.PreAllocateConversion(
                input_pixel_format, TARGET_PIXEL_FORMAT,
                image_width, image_height)

            self._datastream.StartAcquisition()
            self.node_map.FindNode("AcquisitionStart").Execute()
            self.node_map.FindNode("AcquisitionStart").WaitUntilDone()
            self.acquisition_running = True

            print("Acquisition started!")
            return True

        except Exception as e:
            print(f"Exception (start acquisition): {str(e)}")
            return False

    def stop_acquisition(self):
        if self._device is None:
            return
        if not self.acquisition_running:
            return
        try:
            self.node_map.FindNode("AcquisitionStop").Execute()
            self._datastream.StopAcquisition(ids_peak.AcquisitionStopMode_Default)
            # Discard all buffers from the acquisition engine, any associated queue
            # They remain in the announced buffer pool
            self._datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)
            self.acquisition_running = False

            # Unlock parameters
            self.node_map.FindNode("TLParamsLocked").SetValue(0)
        except Exception as e:
            CameraError(f"Failed to stop acquisition: {e}")

    def take_image(self):
        try:
            buffer = self._datastream.WaitForFinishedBuffer(1000)

            # Get image from buffer (shallow copy)
            ipl_image = ids_peak_ipl_extension.BufferToImage(buffer)
            self._datastream.QueueBuffer(buffer)

            return ipl_image

        except Exception as e:
            raise CameraError(f"Failed to make image: {e}")

    ##################################################################
    ####################### Set Parameters ###########################
    ##################################################################
    def set_exposure_time(self, time: int):
        """Sets the camera exposure time in microseconds.
        Precondition: The IDS peak API is initialized and a camera is opened.
        """
        if not self.opened:
            raise CameraError("Cannot set exposure time while camera is closed.")

        try:
            # Get the current exposure time and range
            node = self.node_map.FindNode("ExposureTime")
            min_time = node.Minimum()
            max_time = node.Maximum()
            current_time = node.Value()

            # Set exposure time
            if not (min_time <= time <= max_time):
                raise CameraError(f"Exposure time {time} µs out of bounds ({min_time},{max_time})")
            node.SetValue(time)
            print(f"Exposure time changed: {current_time} µs -> {time} µs")

            # Get increment: If there is no increment, it might be useful to choose a suitable increment for a GUI control element (e.g. a slider)
            # exp_inc = node.Increment() if node.HasConstantIncrement() else 1000

        except Exception as e:
            print(f"Failed to set exposure time: {e}")

    def set_gain(self, gain_value:float, gain_selector="All"):
        if not self.opened:
            raise CameraError("Cannot set gain while camera is closed.")

        try:
            gain_node = self.node_map.FindNode("Gain")
            self.node_map.FindNode("GainSelector").SetCurrentEntry(gain_selector)

            min_gain = gain_node.Minimum()
            max_gain = gain_node.Maximum()
            # inc_gain = gain_node.Increment() if gain_node.HasConstantIncrement() else None
            current_gain = gain_node.Value()

            self._check_bounds("Gain", gain_value, min_gain, max_gain)
            gain_node.SetValue(gain_value)
            print(f"Gain changed: {current_gain} to {gain_value}")

        except Exception as e:
            raise CameraError(f"Failed to set gain: {e}")

    def set_frame_rate(self, rate:float):
        """ Values are in fps."""
        if not self.opened:
            raise CameraError("Cannot set frame rate while camera is closed.")
        try:
            frame_rate_node = self.node_map.FindNode("AcquisitionFrameRate")
            min_rate = frame_rate_node.Minimum()
            max_rate = frame_rate_node.Maximum()
            # inc_rate = frame_rate_node.Increment() if frame_rate_node.HasConstantIncrement() else None

            self._check_bounds("Frame rate", rate, min_rate, max_rate)
            frame_rate_node.SetValue(rate)

        except Exception as e:
            print(f"Failed to set frame rate: {e}")

    def set_roi(self, x:int, y:int, width:int, height:int):
        """The image size determines how large the buffers must be for the image data required by IDS peak during image acquisition.
        Resizing during image acquisition may cause problems if, for example, old buffers are too small after resizing.
        Therefore, resizing is only possible when image acquisition is stopped.

        Before starting the image acquisition, you should free all previous buffers and create new buffers
        according to the newly set image size (see Preparing image acquisition: create buffer).

        If you change the binning or decimation (subsampling) settings, the image size will also change.
        Also in this case, you must recreate the buffers before image acquisition.
        Precondition: image acquisition is stopped
        Postcondition:  Buffers are re-created
                        Acquisition starts again if it was running
        """
        if not self.opened:
            raise CameraError("Cannot set ROI while camera is closed.")
        try:
            # Stop acquisition if running
            was_running = self.acquisition_running
            if self.acquisition_running:
                self.stop_acquisition()

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

            if (x + width > w_max) or (y + height > h_max):
                raise CameraError(f"ROI: (x+width={x + width}, y+height={y + height}) exceeds limits ({w_max},{h_max}).")
            if (width % w_inc != 0) or (height % h_inc != 0):
                raise CameraError(f"ROI: width or/and height ({width}, {height}) not aligned to increments ({w_inc},{h_inc})")
            self._check_bounds("OffsetX", x, x_min, x_max, x_inc)
            self._check_bounds("OffsetY", y, y_min, y_max, y_inc)

            # Set new values
            offset_x_node.SetValue(x)
            offset_y_node.SetValue(y)
            width_node.SetValue(width)
            height_node.SetValue(height)

            # Resume acquisition if it was running before setting new ROI
            if was_running:
                # Recreate buffers (according to the newly set image size)
                self.revoke_buffers()
                self.alloc_buffers()

                self.start_acquisition()

        except Exception as e:
            raise CameraError(f"Failed to set ROI: {e}.")

    def load_user_set(self, cam_setting:str):
        """ Valid settings sets are:
        "Default", "Linescan", "LinescanHighSpeed", "LongExposure", "UserSet0", "UserSet1".
        """
        valid_settings = {"Default", "Linescan", "LinescanHighSpeed", "LongExposure", "UserSet0", "UserSet1"}
        if cam_setting in valid_settings:
            self.node_map.FindNode("UserSetSelector").SetCurrentEntry(cam_setting)
            self.node_map.FindNode("UserSetLoad").Execute()
            self.node_map.FindNode("UserSetLoad").WaitUntilDone()
        else:
            raise CameraError(f"Invalid camera setting '{cam_setting}'. Valid options are: {valid_settings}")

    def save_user_set(self, user_set:str):
        """'UserSet0' or 'UserSet1'"""
        # set selector to user set
        if user_set in {"UserSet0", "UserSet1"}:
            self.node_map.FindNode("UserSetSelector").SetCurrentEntry(user_set)
            self.node_map.FindNode("UserSetSave").Execute()
            self.node_map.FindNode("UserSetSave").WaitUntilDone()
        else:
            raise CameraError(f"Invalid user camera setting '{user_set}'. Valid options are: ('UserSet0', 'UserSet1')")

    def _check_bounds(self, name: str, value: float, min_val: float, max_val: float, increment: float = None):
        if not (min_val <= value <= max_val):
            raise CameraError(f"{name} value={value} out of range [{min_val}, {max_val}]")
        if increment and (value % increment != 0):
            raise CameraError(f"{name} value={value} not aligned to increment {increment}")

    ######################################################
    ############## Transform images ######################
    ######################################################
    def mirror_x(self, image):
        self._image_transformer.MirrorLeftRightInPlace(image)

    def mirror_y(self, image):
        self._image_transformer.MirrorUpDown(image)

    def rotate_180(self, image):
        self._image_transformer.RotateInPlace(image, ids_peak_ipl.ImageTransformer.RotationAngle.Degree180)

    def rotate_90_clockwise(self, image):
        self._image_transformer.RotateInPlace(image, ids_peak_ipl.ImageTransformer.RotationAngle.Degree90Clockwise)

    def rotate_90_counterclockwise(self, image):
        self._image_transformer.RotateInPlace(image, ids_peak_ipl.ImageTransformer.RotationAngle.Degree90Counterclockwise)

    ################################################
    ################ Trigger #######################
    ################################################
    def software_trigger(self):
        self.node_map.FindNode("TriggerSoftware").Execute()
        self.node_map.FindNode("TriggerSoftware").WaitUntilDone()
        print("!! Software trigger !!")
        print(f"acqusition status: {self.acquisition_running}")

    def init_software_trigger(self):
        """Trigger initialization before the acquisition start."""
        was_runnning = False
        if self.acquisition_running:
            was_runnning = True
            self.stop_acquisition()

        self.node_map.FindNode("TriggerSelector").SetCurrentEntry("ExposureStart")
        self.node_map.FindNode("TriggerMode").SetCurrentEntry("On")
        self.node_map.FindNode("TriggerSource").SetCurrentEntry("Software")
        self.trigger_mode = "Software"

        if was_runnning:
            self.start_acquisition()

    def init_hardware_trigger(self, trigger_source="Line0"):
        """
        Trigger initialization before the acquisition start.

        {Counter0Active, Counter1Active, Counter0End, Counter1End,
        Counter0Start, Counter1Start, Line0, Line1, Line2, Line3, PWM0,
        SignalMultiplier0, Software, Timer0Active, Timer1Active, Timer0End,
        Timer1End,Timer0Start, Timer1Start, UserOutput0, UserOutput1, UserOutput2, UserOutput3}"""
        was_runnning = False
        if self.acquisition_running:
            was_runnning = True
            self.stop_acquisition()

        # Activate the XStart trigger and configure its source to an IO line
        self.node_map.FindNode("TriggerSelector").SetCurrentEntry("ExposureStart")
        self.node_map.FindNode("TriggerMode").SetCurrentEntry("On")
        self.node_map.FindNode("TriggerSource").SetCurrentEntry(trigger_source)
        self.trigger_mode = "Hardware"

        if was_runnning:
            self.start_acquisition()

    def wait_for_signal(self):
        while not self.killed:

            try:
                if self.make_image is True:
                    # Call software trigger to load image
                    self.software_trigger()
                    # Get image and save it as file, if that option is enabled
                    image = self.take_image()

                    self.save_image(image)
                    self.save_numpy_as_hdf5(image)
                    self.make_image = False

            except Exception as e:
                self.make_image = False

    ###################### Heplers for manual console execution through main.py ##################
    def ipl2numpy(self, image):
        """ids_peak_ipl.ids_peak_ipl.Image --> numpy array"""
        np_array = image.get_numpy()
        return np_array

    def save_numpy_as_hdf5(self, image, description="test", folder="./test_hdf5"):
        """Save a NumPy array (image) to test HDF5 file with metadata."""
        try:
            np_array = self.ipl2numpy(image)
            os.makedirs(folder, exist_ok=True)
            timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{folder}/test_image_{timestamp}.h5"

            with h5py.File(filename, "w") as f:
                dset = f.create_dataset("image", data=np_array, compression="gzip")
                dset.attrs["description"] = description
                dset.attrs["timestamp"] = timestamp
                dset.attrs["shape"] = str(np_array.shape)
                dset.attrs["dtype"] = str(np_array.dtype)

            print(f"Test image saved to {filename}")
        except Exception as e:
            print(f"EXCEPTION: {e}")

    def get_available_entries(self, node: str):
        """Debug function to list all available entries for nodes like: TriggerSelector, LineMode, LineSelector, TriggerSource etc."""
        # Determine the current entry of Node
        value = self.node_map.FindNode(node).CurrentEntry().SymbolicValue()
        # Get a list of all available entries of Node
        allEntries = self.node_map.FindNode(node).Entries()
        availableEntries = []
        for entry in allEntries:
            if (entry.AccessStatus() != ids_peak.NodeAccessStatus_NotAvailable
                    and entry.AccessStatus() != ids_peak.NodeAccessStatus_NotImplemented):
                availableEntries.append(entry.SymbolicValue())
        print(f"{Node} available entries: {availableEntries} \t current={value}")


import threading
import queue
import numpy as np

class TriggerWorker(threading.Thread):
    """A separate thread that waits for image to be transferred after the trigger."""
    def __init__(self, device, node_map, data_stream, image_queue, keep_image=True, timeout_ms=ids_peak.Timeout.INFINITE_TIMEOUT):
        super().__init__(daemon=True)
        self.device = device
        self.timeout_ms = timeout_ms
        self.running = False
        self.node_map = node_map
        self.data_stream = data_stream
        self.image_queue = image_queue
        self.keep_image = keep_image

    def run(self):
        self.running = True

        print("[Worker] Waiting for trigger ...")
        try:
            while self.running:
                try:
                    # buffer with image?
                    print("[Worker] Attempt to read the buffer...")
                    buffer = self.data_stream.WaitForFinishedBuffer(self.timeout_ms)
                    if buffer is None:
                        print("[Worker] No trigger")
                        continue

                    # Image is transferred, get image from buffer (shallow copy) and free the buffer
                    ipl_image = ids_peak_ipl_extension.BufferToImage(buffer)
                    self.image_queue.put(ipl_image)
                    self.data_stream.QueueBuffer(buffer)

                    # Save image
                    if self.keep_image:
                        print("[Worker] Attempt to save the image ...")
                        self.save_image(ipl_image)

                except ids_peak.TimeoutException:
                    print("[Worker] No trigger for tha last", self.timeout_ms, "ms.")
                    continue
        finally:
            print("[Worker] Stop waiting for trigger ...")

    def stop(self):
        self.running = False

    def save_image(self, image, extension="png"):
        """ Saves image with given extension.
        :param image (ipl_image)
        :param extension (str): png, jpg, bmp"""
        match extension:
            case "png":
                ids_peak_ipl.ImageWriter.WriteAsPNG(self.image_name(".png"), image)
            case "jpg":
                ids_peak_ipl.ImageWriter.WriteAsJPG(self.image_name(".jpg"), image)
            case "bmp":
                ids_peak_ipl.ImageWriter.WriteAsBMP(self.image_name(".bmp"), ipl_image)
        print("Image saved!")

    def image_name(self, ext: str) -> str:
        path = "/home/apq/labscript-suite/userlib/user_devices/ids_camera/images/"
        today_str = dt.now().strftime("%Y-%m-%d")
        pattern = f"{today_str}_"

        # count how many images with this data exist
        existing = [f for f in os.listdir(path) if f.startswith(pattern) and f.endswith(ext)]
        index = len(existing) + 1

        filename = f"{today_str}_{index}{ext}"
        full_path = os.path.join(path, filename)

        return full_path
