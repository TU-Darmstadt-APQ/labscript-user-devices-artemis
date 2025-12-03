#from labscript import AnalogOut
from labscript_devices import register_classes
from labscript import Device, set_passed_properties, config
from labscript import IntermediateDevice
from labscript import AnalogOut
from labscript import LabscriptError
import time
import numpy as np
import h5py
import os
from user_devices.logger_config import logger



class CAEN(IntermediateDevice):
    description = 'CAEN_R8034'
    allowed_children = [AnalogOut]

    @set_passed_properties({"connection_table_properties": ["port", "baud_rate", "pid", "vid", "serial_number", "bipol", "ramp_up", "ramp_down"],
                            "device_properties": []})
    def __init__(self, name, port=None, vid=None, pid=None, baud_rate=9600, serial_number=None, bipol=False, parent_device=None, ramp_up:int=10, ramp_down:int=10, connection=None, **kwargs):
        IntermediateDevice.__init__(self, name, parent_device, **kwargs)
        self.serial_number = serial_number
        self.bipol = bipol
        self.ramp_up = ramp_up
        self.ramp_down = ramp_down
        if port is not None:
            self.BLACS_connection = '%s,%s' % (port, baud_rate)
        else:
            self.BLACS_connection = '%s,%s' % (vid, pid)

    def add_device(self, device):
        Device.add_device(self, device)

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

        # create dataset for values from manual
        AO_manual_table = self._make_analog_out_table_from_manual(analogs)
        group.create_dataset("AO_manual", shape=AO_manual_table.shape, maxshape=(None,), dtype=AO_manual_table.dtype,
                             compression=config.compression, chunks=True)


    def _make_analog_out_table_from_manual(self, analogs):
        """Create a structured empty numpy array with first column as 'time', followed by analog channel data.
        Args:
            times (array-like): Array of timestamps.
            ...
        Returns:
            np.ndarray: Structured empty array with time and analog outputs."""

        str_dtype = h5py.string_dtype(encoding='utf-8', length=19)

        dtypes = [('time', str_dtype)] + [(c, np.float32) for c in analogs]

        analog_out_table = np.empty(0, dtype=dtypes)
        return analog_out_table