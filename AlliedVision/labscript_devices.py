from labscript import Device, set_passed_properties, TriggerableDevice
from labscript import LabscriptError
from labscript_utils import dedent
import numpy as np
import h5py
from enum import Enum
import sys


class TriggerActivationType(str, Enum):
    FALLING_EDGE = 'FallingEdge'
    RISING_EDGE = 'RisingEdge'

class AVVisibilityLevelType(str, Enum):
    BEGINNER = 'Beginner'
    EXPERT = 'Expert'
    GURU = 'Guru'
    INVISIBLE = 'Invisible'

class AlviumCamera(TriggerableDevice):
    description = 'Allied Vision Camera U-319m'
    allowed_children = []

    @set_passed_properties(
        property_names={
            "connection_table_properties": [
                "camera_id",
                "orientation",
                "manual_mode_gain",
                "manual_mode_exposure_time",
                "trigger_gpio",
                "visibility_level",
                "trigger_activation",
            ],
            "device_properties": [
                "gain",
                "exposure_time",
                "stop_acquisition_timeout",
                "framerate",
            ],
        }
    )
    def __init__(
            self,
            name,
            parent_device,
            connection,
            camera_id,
            trigger_gpio=0,
            gain=10,
            exposure_time=5e3,
            framerate=0,
            manual_mode_gain=10,
            manual_mode_exposure_time=5e3,
            orientation=None,
            trigger_activation=TriggerActivationType.FALLING_EDGE,
            stop_acquisition_timeout=5.0,
            visibility_level=AVVisibilityLevelType.EXPERT,
            trigger_duration=None,
            **kwargs
    ):
        """

        :param name:
        :param parent_device:
        :param connection:
        :param camera_id:
        :param trigger_gpio:
        :param gain:
        :param exposure_time: in seconds
        :param framerate: can be unlimited, if 0
        :param manual_mode_gain:
        :param manual_mode_exposure_time:
        :param orientation:
        :param trigger_activation: (TriggerActivationType)
        :param stop_acquisition_timeout: (float|int) in seconds
        :param visibility_level: (VisibilityLevelType)
        :param kwargs:
        """
        self.trigger_activation = trigger_activation
        self.orientation = orientation
        self.camera_id = camera_id
        self.BLACS_connection = camera_id

        self.gain = gain
        self.exposure_time = exposure_time
        self.framerate = framerate
        self.manual_mode_gain = manual_mode_gain
        self.manual_mode_exposure_time = manual_mode_exposure_time
        self.visibility_level = visibility_level
        self.stop_acquisition_timeout = stop_acquisition_timeout
        self.trigger_gpio = trigger_gpio

        self.trigger_duration = trigger_duration
        self.parent_device = parent_device

        self.exposures = []
        TriggerableDevice.__init__(self, name, parent_device, connection, **kwargs)

    # def expose(self, t, name, frametype='frame', trigger_duration=None):
    #     """Request an exposure at the given time. A trigger will be produced by the
    #     parent trigger object, with duration trigger_duration, or if not specified, of
    #     self.trigger_duration. The frame should have a `name, and optionally a
    #     `frametype`, both strings. These determine where the image will be stored in the
    #     hdf5 file. `name` should be a description of the image being taken, such as
    #     "insitu_absorption" or "fluorescence" or similar. `frametype` is optional and is
    #     the type of frame being acquired, for imaging methods that involve multiple
    #     frames. For example an absorption image of atoms might have three frames:
    #     'probe', 'atoms' and 'background'. For this one might call expose three times
    #     with the same name, but three different frametypes.
    #     """
    #     # Backward compatibility with code that calls expose with name as the first
    #     # argument and t as the second argument:
    #     if isinstance(t, str) and isinstance(name, (int, float)):
    #         msg = """expose() takes `t` as the first argument and `name` as the second
    #             argument, but was called with a string as the first argument and a
    #             number as the second. Swapping arguments for compatibility, but you are
    #             advised to modify your code to the correct argument order."""
    #         print(dedent(msg), file=sys.stderr)
    #         t, name = name, t
    #     if trigger_duration is None:
    #         trigger_duration = self.trigger_duration
    #     if trigger_duration is None:
    #         msg = """%s %s has not had an trigger_duration set as an instantiation
    #             argument, and none was specified for this exposure"""
    #         raise ValueError(dedent(msg) % (self.description, self.name))
    #     if not trigger_duration > 0:
    #         msg = "trigger_duration must be > 0, not %s" % str(trigger_duration)
    #         raise ValueError(msg)
    #     self.trigger(t, trigger_duration)
    #     self.exposures.append((t, name, frametype, trigger_duration))
    #     return trigger_duration

    def expose(self, t, name, frametype='frame', trigger_duration=None):
        """Request an exposure at the given time. A trigger will be produced by the
                parent trigger object, with duration trigger_duration, or if not specified, of
                self.trigger_duration. The frame should have a `name, and optionally a
                `frametype`, both strings. These determine where the image will be stored in the
                hdf5 file. `name` should be a description of the image being taken, such as
                "insitu_absorption" or "fluorescence" or similar. `frametype` is optional and is
                the type of frame being acquired, for imaging methods that involve multiple
                frames. For example an absorption image of atoms might have three frames:
                'probe', 'atoms' and 'background'. For this one might call expose three times
                with the same name, but three different frametypes.
                """
        # Backward compatibility with code that calls expose with name as the first
        # argument and t as the second argument:
        if isinstance(t, str) and isinstance(name, (int, float)):
            msg = """expose() takes `t` as the first argument and `name` as the second
                        argument, but was called with a string as the first argument and a
                        number as the second. Swapping arguments for compatibility, but you are
                        advised to modify your code to the correct argument order."""
            print(dedent(msg), file=sys.stderr)
            t, name = name, t
        if trigger_duration is None:
            trigger_duration = self.trigger_duration
        if trigger_duration is None:
            msg = """%s %s has not had an trigger_duration set as an instantiation
                        argument, and none was specified for this exposure"""
            raise ValueError(dedent(msg) % (self.description, self.name))
        if not trigger_duration > 0:
            msg = "trigger_duration must be > 0, not %s" % str(trigger_duration)
            raise ValueError(msg)
        # self.trigger(t, trigger_duration) fixme
        self.exposures.append((t, name, frametype, trigger_duration))
        return trigger_duration

    def generate_code(self, hdf5_file):
        if self.parent_device:
            self.do_checks()
        vlenstr = h5py.special_dtype(vlen=str)
        table_dtypes = [
            ('t', float),
            ('name', vlenstr),
            ('frametype', vlenstr),
            ('trigger_duration', float),
        ]
        data = np.array(self.exposures, dtype=table_dtypes)
        group = self.init_device_group(hdf5_file)
        if self.exposures:
            group.create_dataset('EXPOSURES', data=data)