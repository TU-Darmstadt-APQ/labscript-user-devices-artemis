from user_devices.BS_cryo_old.labscript_devices import BS_cryo
import json
import os

THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
CAPABILITIES_FILE = os.path.join(THIS_FOLDER, 'capabilities.json')
with open(CAPABILITIES_FILE, 'r') as f:
    CAPABILITIES = json.load(f).get('BS_1_10', {})


class BS_1_10(BS_cryo):
    description = 'BS_1_10'

    def __init__(self, *args, **kwargs):
        """Class for BS 1-10 cryo bias supply"""
        combined_kwargs = CAPABILITIES.copy()
        combined_kwargs.update(kwargs)
        BS_cryo.__init__(self, *args, **combined_kwargs)