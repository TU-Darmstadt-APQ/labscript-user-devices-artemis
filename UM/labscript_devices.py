from labscript_devices import register_classes
from labscript import Device, set_passed_properties
from labscript import IntermediateDevice

class UM(Device): 
    """ A labscript device to send commands to device at the beginning and end of the shots."""
    description = 'UM'
    
    @set_passed_properties({"connection_table_properties": ["port", "baud_rate"]})
    def __init__(self, name, port='', baud_rate=9600, parent_device=None, connection=None, **kwargs):
        Device.__init__(self, name, parent_device, connection, **kwargs)
        self.BLACS_connection = '%s,%s' % (port, str(baud_rate))
    
    def add_device(self, device):
        Device.add_device(self, device)

    def generate_code(self, hdf5_file):
        """Convert the list of commands into numpy arrays and save them to the shot file."""
        Device.generate_code(self, hdf5_file)