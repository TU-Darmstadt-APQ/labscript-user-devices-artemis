# from PyQt5.QtQml import kwargs
from labscript_devices import register_classes
from labscript import Device, set_passed_properties
from labscript import IntermediateDevice
from labscript_devices.PulseBlaster import PulseBlaster

class BNC_575(PulseBlaster):
    # I have no idea if it suitable for this exact device
    description = 'BNC_575'
    clock_limit = 8.3e6
    core_clock_freq = 100

    @set_passed_properties(property_names={
        "connection_table_properties": ["port", "baud_rate"]
        }
    )
    def __init__(self, name, port='', baud_rate=None, parent_device=None, trigger_connection=None, programming_scheme=None, pulse_width=None):
        super().__init__(self, name, parent_device)
        self.BLACS_connection = '%s,%s' % (port, str(baud_rate))
    
    def add_device(self, device):
        Device.add_device(self, device)

    def generate_code(self, hdf5_file):
        Device.generate_code(self, hdf5_file)

    def pseudoclock(self):
        return self._pseudoclock

    def convert_to_pg_inst(self, dig_outputs):
        pg_inst = []
        # TODO: What to do ?

    def write_pg_inst_to_h5(self, pg_inst, hdf5_file):
        # NOW WE SQUEEZE the instruction into a nympy array ready for writing to hdf5.
        pg_dtype = [('dly', np.int32),
                    ('wdth', np.int32),
                    ('rt', np.int32)]
        pg_inst_table = np.empty(len(pg_inst), dtype=pg_dtype)
