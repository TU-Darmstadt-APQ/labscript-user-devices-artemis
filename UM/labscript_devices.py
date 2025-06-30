from labscript_devices import register_classes
from labscript import Device, set_passed_properties
from labscript import IntermediateDevice, AnalogOut, config
import numpy as np

class UM(IntermediateDevice):
    """ A labscript device to send commands to device at the beginning and end of the shots."""
    description = 'UM'
    allowed_children = [AnalogOut]
    @set_passed_properties({"connection_table_properties": ["port", "baud_rate"]})
    def __init__(self, name, port='', baud_rate=9600, parent_device=None, **kwargs):
        IntermediateDevice.__init__(self, name, parent_device, **kwargs)
        self.BLACS_connection = '%s,%s' % (port, str(baud_rate))


    def generate_code(self, hdf5_file):
        """Convert the list of commands into numpy arrays and save them to the shot file."""
        IntermediateDevice.generate_code(self, hdf5_file)

        clockline = self.parent_device
        pseudoclock = clockline.parent_device
        times = pseudoclock.times[clockline]
        n_timepoints = len(times)

        # create dataset
        analogs = {}
        for child_device in self.child_devices:
            if isinstance(child_device, AnalogOut):
                analogs[child_device.connection] = child_device

        dtypes = [('time', np.float64)] + [(c, np.float32) for c in analogs]  # first column = time

        analog_out_table = np.empty(n_timepoints, dtype=dtypes)

        analog_out_table['time'] = times
        for connection, output in analogs.items():
            analog_out_table[connection] = output.raw_output

        group = self.init_device_group(hdf5_file)
        group.create_dataset("AO_buffered", data=analog_out_table, compression=config.compression)