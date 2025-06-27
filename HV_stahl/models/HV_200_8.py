from user_devices.HV_stahl.labscript_devices import HV_
import json
import os

THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
CAPABILITIES_FILE = os.path.join(THIS_FOLDER, 'capabilities.json')
with open(CAPABILITIES_FILE, 'r') as f:
    CAPABILITIES = json.load(f).get('HV_200_8', {})


class HV_200_8(HV_):
    description = 'HV_200_8'

    def __init__(self, *args, **kwargs):
        """Class for HV 200 8"""
        combined_kwargs = CAPABILITIES.copy()
        combined_kwargs.update(kwargs)
        HV_.__init__(self, *args, **combined_kwargs)