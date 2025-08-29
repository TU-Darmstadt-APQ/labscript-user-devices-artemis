from labscript import Device, AnalogOut, DigitalOut, AnalogIn
from labscript import LabscriptError


class PicoScope4224A(Device):
    """ """

    @set_passed_properties({"connection_table_properties": ["serial_number"]})
    def __init__(self, name, parent_device=None, serial_number=None, **kwargs):
        super().__init__(name, parent_device, **kwargs)
