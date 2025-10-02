from labscript_devices import register_classes
from labscript import Device, set_passed_properties, config
from labscript import TriggerableDevice
from labscript import LabscriptError

class AlliedVision(TriggerableDevice):
    description = 'Allied Vision Camera U-319m'
    allowed_children = []

    def __init__(self, name, parent_device=None, connection=None, **kwargs):
        super().__init__(name, parent_device, connection, **kwargs)

    def generate_code(self, hdf5_file):
        super().generate_code(hdf5_file)