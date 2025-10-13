from labscript_devices import register_classes
from labscript import Device, set_passed_properties, config
from labscript import TriggerableDevice
from labscript import LabscriptError
import time
import numpy as np
import sys
from labscript_utils import dedent
import h5py
from user_devices.logger_config import logger
from datetime import datetime


class IDSCamera(TriggerableDevice):
    description = 'IDS Camera'
    allowed_children = []

    @set_passed_properties(
        property_names={
            "connection_table_properties": [
                "serial_number",
                "name"
            ],
            "device_properties": [
                "exposure_time",
                "frame_rate",
                "gain",
                "roi",
                "camera_setting"
            ],
        }
    )
    def __init__(self, name, parent_device=None, connection=None, serial_number="4104380609", exposure_time_ms=None, roi=None, frame_rate=None, gain=None, camera_setting="Default", **kwargs):
        super().__init__(name, parent_device, connection, **kwargs)
        self.serial_number = serial_number

        self.exposure_time = exposure_time_ms
        self.frame_rate = frame_rate
        self.gain = gain
        self.roi = roi
        self.camera_setting = camera_setting
        self.BLACS_connection = '%s' % connection
   
    # def expose(self, t, name, frametype='frame'):
    #     """Request an exposure at the given time. A software trigger will be produced.
    #     The frame should have a `name, and optionally a `frametype`, both strings.
    #     These determine where the image will be stored in the hdf5 file.
    #     `name` should be a description of the image being taken, such as
    #     "insitu_absorption" or "fluorescence" or similar. `frametype` is optional and is
    #     the type of frame being acquired, for imaging methods that involve multiple
    #     frames. For example an absorption image of atoms might have three frames:
    #     'probe', 'atoms' and 'background'. For this one might call expose three times
    #     with the same name, but three different frametypes.
    #     """
    #     # Backward compatibility with code that calls expose with name as the first
    #     # argument and t as the second argument:
    #     if isinstance(t, str) and isinstance(name, (int, float)):
    #         msg = """expose() takes `t` as the first argument and `name` as the second
    #             argument, but was called with a string as the first argument and a
    #             number as the second. Swapping arguments for compatibility, but you are
    #             advised to modify your code to the correct argument order."""
    #         print(dedent(msg), file=sys.stderr)
    #         t, name = name, t
    #
    #     self.software_trigger(t) # todo:
    #     self.exposures.append((t, name, frametype))

    def generate_code(self, hdf5_file): #fixme: not sure if it works like this
        super().generate_code(hdf5_file)
