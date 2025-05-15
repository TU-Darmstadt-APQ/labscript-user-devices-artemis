# from PyQt5.QtQml import kwargs
from fontTools.ttLib.tables.ttProgram import instructions
from labscript_devices import register_classes
from labscript import Device, set_passed_properties
from labscript import IntermediateDevice, config, PseudoclockDevice
from labscript_devices.PulseBlaster import PulseBlaster
from labscript_devices.PulseBlaster_No_DDS import PulseBlaster_No_DDS

class BNC_575(PulseBlaster):

    pg_instructions = {'START': 0,
                       'END': 1,
                       'RESET': 2,
                       'SET_MODE': 3,
                       'SET_DELAY': 4, # each channel
                       'SET_WIDTH': 5 # each channel
                       }
    description = 'BNC_575 Pulse Generator'
    # TODO: hsould be hardcoded, or we can set?
    n_flags = 9
    core_clock_freq = 100 # MHz

    @set_passed_properties(property_names={
        "connection_table_properties": ["port", "baud_rate"]
        }
    )
    def __init__(self, name, port='', connection=None, baud_rate=None, parent_device=None):
        super().__init__(name, parent_device)
        self.BLACS_connection = '%s,%s' % (port, str(baud_rate))
       # self._direct_output_device = ??? #TODO

    def add_device(self, device):
        Device.add_device(self, device)

    # def direct_outputs(self):
    #     return self._direct_output_device
    #
    def get_direct_outputs(self):
        """"Finds out which outputs are directly attached to the Pulse Generator"""
        return PulseBlaster.get_direct_outputs()

    def convert_to_pg_inst(self, do_outputs):
        # TODO: what this function does exactly, in which format
        return PulseBlaster.convert_to_pb_inst(do_outputs, [], {}, {}, {})

    def write_pg_inst_to_h5(self, pg_inst, hdf5_file):
        pg_type = [
            ('flags', np.int32),  # which flags to adress (0:internal, 1-8:channels)
            ('inst', np.int32), # instructions in int
            ('inst_data', np.int32), # parameters for instructions (e.g. width, delay)
            ('length', np.float64) # delay length (for instructions)
        ]
        pg_inst_table = np.empty(len(pg_inst), dtype=pg_type)
        for i, inst in enumerate(pg_inst):
            flagint = int(inst['flags'])
            instructionint = self.pg_instructions[inst['instruction']]
            dataint = inst['data']
            delaydouble = inst['delay']
            pg_inst_table[i] = (flagint, instructionint, dataint, delaydouble)

        group = hdf5_file['/devices/'+self.name]
        group.create_dataset('PULSE_PROGRAM', compression=config.compression, data=pg_inst_table)

    def generate_code(self, hdf5_file):
        self.init_device_group(hdf5_file)
        PseudoclockDevice.generate_code(self, hdf5_file)
        do_outputs, _ = self.get_direct_outputs()
        logger.info(f"Direct outputs of BNC_575: {do_outputs}")
        pg_inst = self.convert_to_pg_inst(do_outputs, [], {}, {}, {}) # from PulseBlaster
        self.write_pg_inst_to_h5(pg_inst, hdf5_file)




