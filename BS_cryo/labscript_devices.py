from labscript_devices import register_classes
from labscript import Device, set_passed_properties, IntermediateDevice, AnalogOut, config
from labscript import IntermediateDevice
import h5py
import numpy as np
from labscript_devices.NI_DAQmx.utils import split_conn_DO, split_conn_AO
from user_devices.logger_config import logger
from user_devices.Stahl_HV.labscript_devices import AnalogOutStahl


class BS_cryo(IntermediateDevice):
    description = 'BS_cryo_bias_supply'
    allowed_children = [AnalogOutStahl, AnalogOut]

    @set_passed_properties(
        property_names={
            "connection_table_properties": [
                "baud_rate",
                "port",
                "vid",
                "pid",
                "num_ao",
                "ao_range",
                "serial_number",
                "pre_programmed",
            ],
        }
    )
    def __init__(
            self,
            name,
            port='',
            baud_rate=9600,
            parent_device=None,
            vid=None,
            pid=None,
            num_ao=None,
            ao_range=None,
            serial_number=None,
            pre_programmed=False,
            **kwargs
    ):
        super().__init__(name, parent_device, **kwargs)
        if port:
            self.BLACS_connection = '%s,%s' % (port, str(baud_rate))
        if vid and pid:
            self.BLACS_connection = '%s,%s' % (vid, pid)

        self.ao_range = ao_range
        self.num_ao = num_ao
        self.port = port
        self.vid = vid
        self.pid = pid
        self.baud_rate = baud_rate
        self.serial_number = serial_number
        self.pre_programmed = pre_programmed

    def add_device(self, device):
        super().add_device(device)

    def generate_code(self, hdf5_file):
        """Convert the list of commands into numpy arrays and save them to the shot file."""
        logger.info("[BS_cryo_old] generate_code for BS cryo is called")
        IntermediateDevice.generate_code(self, hdf5_file)

        clockline = self.parent_device
        pseudoclock = clockline.parent_device
        times = pseudoclock.times[clockline]

        # create dataset
        analogs = {}
        for child_device in self.child_devices:
            if isinstance(child_device, AnalogOut):
                analogs[child_device.connection] = child_device

        AO_table = self._make_analog_out_table(analogs, times)
        AO_manual_table = self._make_analog_out_table_from_manual(analogs)

        group = self.init_device_group(hdf5_file)
        group.create_dataset("AO_buffered", data=AO_table, compression=config.compression)
        group.create_dataset("AO_manual", shape=AO_manual_table.shape, maxshape=(None,), dtype=AO_manual_table.dtype,
                             compression=config.compression, chunks=True)

    def _make_analog_out_table(self, analogs, times):
        """Create a structured numpy array with first column as 'time', followed by analog channel data.
        Args:
            analogs (dict): Mapping of connection names to AnalogOut devices.
            times (array-like): Array of time points.
        Returns:
            np.ndarray: Structured array with time and analog outputs.
        """
        if not analogs:
            return None

        n_timepoints = len(times)
        dtypes = [('time', np.float64)] + [(c, np.float32) for c in analogs]  # first column = time
        analog_out_table = np.empty(n_timepoints, dtype=dtypes)
        analog_out_table['time'] = times

        for connection, output in analogs.items():
            analog_out_table[connection] = output.raw_output

        return analog_out_table

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