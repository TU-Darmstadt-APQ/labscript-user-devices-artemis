from labscript_devices import register_classes
from labscript import Device, set_passed_properties, config
from labscript import IntermediateDevice
from labscript import AnalogOut
from labscript import LabscriptError
import time
import numpy as np
import os
from user_devices.logger_config import logger



class Camera():
    description = ''
    allowed_children = []

    @set_passed_properties({"connection_table_properties": []})
    def __init__(self, name, parent_device=None, connection=None, **kwargs):
        super().__init__(name, parent_device, **kwargs)
   
    def add_device(self, device):
        Device.add_device(self, device)

    def generate_code(self, hdf5_file):
        pass
