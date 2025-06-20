from fontTools.ttLib.tables.ttProgram import instructions
from labscript_devices import register_classes
from labscript import Device, set_passed_properties, DigitalOut
from labscript import TriggerableDevice, config
import numpy as np
from user_devices.logger_config import logger

class PulseChannel(DigitalOut):
    description = 'Channel of BNC_575'

    def __init__(
            self,
            name,
            parent_device,
            connection,
            delay,
            width,
            mode='NORMal',
            burst_count=None,
            on_count=None,
            off_count=None,
            polarity='NORMal',
            output_mode='TTL',
            amplitude=None,
            sync_source='T0',
            **kwargs
    ):
        """

        :param name:
        :param parent_device:
        :param connection:
        :param delay:
        :param width:
        :param mode: NORMal / SINGle / BURSt / DCYCle
        :param burst_count:
        :param on_count:
        :param off_count:
        :param polarity: NORMal /COMPlement /INVerted
        :param output_mode: TTL/ ADJustable/
        :param amplitude: 2.0V to 20V
        :param sync_source: TO, CHA, CHB, CHC, CHD, etc
        :param kwargs:
        """
        DigitalOut.__init__(self, name, parent_device, connection, **kwargs)
        self.properties = {
            'mode': mode,
            'delay': delay,
            'width': width,
            'burst_count': burst_count,
            'on_count': on_count,
            'off_count': off_count,
            'polarity': polarity,
            'sync_source': sync_source,
            'output_mode': output_mode,
            'amplitude': amplitude,
        }

class BNC_575(TriggerableDevice):
    description = 'BNC575-Pulse-Generator'
    allowed_children = [PulseChannel]
    @set_passed_properties(
        property_names={"connection_table_properties": ["port",
                                                        "baud_rate",
                                                        "trigger_mode",
                                                        "t0_mode",
                                                        "t0_period",
                                                        "t0_burst_count",
                                                        "t0_on_count",
                                                        "t0_off_count",
                                                        "trigger_logic",
                                                        "trigger_level"]}
                )
    def __init__(self,
                 name, # !!!
                 port='', # !!!
                 baud_rate=115200,
                 trigger_device=None,
                 trigger_connection=None,
                 trigger_mode='DISabled', # !!!
                 trigger_logic='RISing',
                 trigger_level=5,
                 t0_mode='NORMal', # !!!
                 t0_period=1e-3, # !!!
                 t0_burst_count=None,
                 t0_on_count=None,
                 t0_off_count=None,
                 **kwargs): # NOTE: if extended --> self.t0_config, system_dtypes, channel_dtypes
        """

        :param name:
        :param port:
        :param baud_rate:
        :param trigger_device:
        :param trigger_connection:
        :param trigger_mode: DISabled / TRIGgered
        :param trigger_logic: RISing / FALLing
        :param trigger_level:
        :param t0_mode: NORMal / SINGle / BURSt / DCYCle
        :param t0_period: 100ns-5000s
        :param t0_burst_count:
        :param t0_on_count:
        :param t0_off_count:
        :param kwargs:
        """
        self.t0_config = {
            'mode': t0_mode,
            'period': t0_period,
            'burst_count': t0_burst_count,
            'on_count': t0_on_count,
            'off_count': t0_off_count,
            'trigger_mode': trigger_mode,
            'trigger_logic': trigger_logic,
            'trigger_level': trigger_level,
            'trigger_device': trigger_device
        }
        TriggerableDevice.__init__( self, name, parent_device=None, connection=None, parentless=True, **kwargs)
        self.BLACS_connection = '%s,%s' % (port, str(baud_rate))
        self.trigger_connection = '%s' % (trigger_connection)

    def add_device(self, device):
        Device.add_device(self, device)

    def trigger(self, t):
        pass

    def generate_code(self, hdf5_file):
        #TriggerableDevice.generate_code(self, hdf5_file)

        # system configuration
        system_dtypes = [
            ('mode', np.dtype('S20')),
            ('period', np.float64),
            ('burst_count', np.int32),
            ('on_count', np.int32),
            ('off_count', np.int32),
            ('trigger_mode', np.dtype('S20')),
            ('trigger_logic', np.dtype('S20')),
            ('trigger_level', np.int32)
        ]

        system_configuration = np.empty(1, dtype=system_dtypes)

        for k, v in self.t0_config.items():
            if k not in system_configuration.dtype.names:
                continue

            if v is None:
                field_type = system_configuration.dtype[k]

                if np.issubdtype(field_type, np.integer):
                    system_configuration[0][k] = -1
                elif np.issubdtype(field_type, np.floating):
                    system_configuration[0][k] = np.nan
                elif np.issubdtype(field_type, np.dtype('S').type):  # U type
                    system_configuration[0][k] = ""
                else:
                    raise ValueError(f"Unhandled dtype for '{k}': {field_type}")
            else:
                if isinstance(v, str):
                    v = v.encode('utf-8')
                system_configuration[0][k] = v


        # channel configuration
        self.output_num = len(self.child_devices)
        channels_dtypes = [ #should be the same as 'properties' attribute of PulseChannel
            ('channel', np.int32),
            ('mode', np.dtype('S20')),
            ('delay', np.float64),
            ('width', np.float64),
            ('burst_count', np.int32),
            ('on_count', np.int32),
            ('off_count', np.int32),
            ('polarity', np.dtype('S20')),
            ('sync_source', np.dtype('S20')),
            ('output_mode', np.dtype('S20')),
            ('amplitude', np.int32),
        ]

        channels_configuration = np.empty(self.output_num, channels_dtypes)
        for idx, child in enumerate(self.child_devices):
            print(f"{child} with index={idx} and properties:  {child.properties}")
            channels_configuration[idx]['channel'] = idx + 1

            for k in channels_configuration.dtype.names:
                if k == 'channel':
                    continue  # already set
                v = child.properties.get(k)

                if v is None:
                    field_type = channels_configuration.dtype[k]
                    if np.issubdtype(field_type, np.integer):
                        channels_configuration[idx][k] = -1
                    elif np.issubdtype(field_type, np.floating):
                        channels_configuration[idx][k] = np.nan
                    elif np.issubdtype(field_type, np.dtype('S').type):
                        channels_configuration[idx][k] = ""
                    else:
                        raise ValueError(f"Unhandled dtype for {k}: {field_type}")
                else:
                    if isinstance(v, str):
                        v = v.encode('utf-8')

                    channels_configuration[idx][k] = v

        group = self.init_device_group(hdf5_file)
        group.create_dataset("system_timer", data=system_configuration, compression=config.compression)
        group.create_dataset("channel_timer", data=channels_configuration, compression=config.compression)


