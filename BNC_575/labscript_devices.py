# from PyQt5.QtQml import kwargs
from labscript_devices import register_classes
from labscript import Device, set_passed_properties
from labscript import IntermediateDevice
from labscript_devices.PulseBlaster import PulseBlaster
from labscript_devices.PulseBlaster_No_DDS import PulseBlaster_No_DDS

class BNC_575(IntermediateDevice):
    # I have no idea if it suitable for this exact device
    description = 'BNC_575 Pulse Generator'

    @set_passed_properties(property_names={
        "connection_table_properties": ["port", "baud_rate"]
        }
    )
    def __init__(self, name, port='', connection=None, baud_rate=None, parent_device=None):
        super().__init__(name, parent_device)
        self.BLACS_connection = '%s,%s' % (port, str(baud_rate))
        self.start_commands = [] # Im not sure if I really need this?

    def add_device(self, device):
        Device.add_device(self, device)

    def generate_code(self, hdf5_file):
        # # Generate the hardware instructions
        # super().generate_code(self, hdf5_file)
        # start_commands = np.array(self.start_commands)
        # group = self.init_device_group(hdf5_file)
        # if self.start_commands:
        #     group.create_dataset("START_COMMANDS", data=start_commands)
        return

    def add_start_command(self, command):
        """Add a serial command that should be send at the start of the experiment.
        Commads in the form of strings, i guess"""
        self.start_commands.append(command)



