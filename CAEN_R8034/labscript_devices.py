#from labscript import AnalogOut
from labscript_devices import register_classes
from labscript import Device, set_passed_properties, config
from labscript import IntermediateDevice
from labscript import AnalogOut
import time
import numpy as np
import os


class CAEN(IntermediateDevice): #TODO: do we really need to clock this things up? if else: change IntermediateDevice -> Device
    description = 'CAEN_R8034'
    #allowed_children = [AnalogOut]
    
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
        self.num_AO = 4
   
    def add_device(self, device):
        Device.add_device(self, device)

    def generate_code(self, hdf5_file):
        """Convert the lists of commands into numpy arrays and save them to the shot file.
        Or packes the recorded values into the hdf5 file(into device properties).
        Args:
             hdf5_file: used file format
        """
        # Словарь, в который соберем все аналоговые выходы
        analog_outs = {}

        if len(self.child_devices) == 0:
            raise LabscriptError(f'{self.name} has no child devices connected.')

        # Получаем ссылки на все AnalogOut
        for output in self.child_devices:
            channel = output.connection # 'CH0'
            connection = int(channel[2:]) # 'CH0' --> 0
            if not isinstance(output, AnalogOut):
                raise LabscriptError(f'Device {output.name} is not an AnalogOut.')
            analog_outs[connection] = output

        # get time points from parent pseudoclock
        parent_clockline = self.parent_device
        if parent_clockline is None:
            raise LabscriptError(f'{self.name} has no parent clockline.')

        times = parent_clockline.parent_device.times[parent_clockline]
        num_points = len(times)

        # Create structure if numpy array with certain type for each channel
        dtypes = []
        for i in range(self.num_AO):
            dtypes.append(('CH%d' % i, np.float32))
        analog_data = np.zeros(num_points, dtype=dtypes)

        # Fill values for each channel at each time point
        for ch, output in analog_outs.items():
            values = output.raw_output
            if len(values) != num_points:
                raise LabscriptError(f'{output.name} has incorrect number of data points.')
            analog_data[f'CH{ch}'][:] = values

        # Создаём группу и сохраняем данные
        grp = self.init_device_group(hdf5_file)
        grp.create_dataset('TIMES', data=times, compression=config.compression)
        grp.create_dataset('ANALOG_OUTPUTS', data=analog_data, compression=config.compression)

        # print(f"[CAEN generate_code] TIMES:\n{times}")
        # print(f"[CAEN generate_code] ANALOG_OUTPUTS:\n{analog_data}")

        with open(TMP_DIR, 'w') as f:
            f.write(f"[CAEN generate_code] TIMES:\n{times}\n")
            f.write(f"[CAEN generate_code] ANALOG_OUTPUTS:\n{analog_data}\n")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(BASE_DIR, 'caen_debug_output.txt')
