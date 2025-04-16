from labscript_devices import register_classes
from labscript import Device, set_passed_properties
from labscript import IntermediateDevice

class CAEN(Device):
    description = 'CAEN_R8034'
    
    # @set_passed_properties({"connection_table_properties": ["port", "baud_rate"]})
    # def __init__(self, name, port='', baud_rate=9600, parent_device=None, connection=None):
    #     Device.__init__(self, name, parent_device, connection)
    #     self.BLACS_connection = '%s,%s' % (port, str(baud_rate))
    
    # def add_device(self, device):
    #     Device.add_device(self, device)

    # def generate_code(self, hdf5_file):
    #     Device.generate_code(self, hdf5_file)

    @set_passed_properties({"connection_table_properties": ["port", "baud_rate", "vid", "pid"]})
    def __init__(self, name, port='', baud_rate=None, vid=None, pid=None, parent_device=None, connection=None):
        Device.__init__(self, name, parent_device, connection)
        self.BLACS_connection = f"{port},{baud_rate},{vid},{pid}"    
   
    def add_device(self, device):
        Device.add_device(self, device)

    def generate_code(self, hdf5_file):
        Device.generate_code(self, hdf5_file)