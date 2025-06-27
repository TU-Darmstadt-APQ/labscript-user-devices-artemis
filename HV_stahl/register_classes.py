from labscript_devices import register_classes
import json
import os
from user_devices.logger_config import logger

THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
CAPABILITIES_FILE = os.path.join(THIS_FOLDER, 'models', 'capabilities.json')

capabilities = {}
if os.path.exists(CAPABILITIES_FILE):
    with open(CAPABILITIES_FILE) as f:
        capabilities = json.load(f)

register_classes(
    "HV_",
    BLACS_tab='user_devices.HV_stahl.BLACS_tabs.HV_Tab',
    runviewer_parser=None,
)

for model_name in capabilities:
    logger.debug(f"Registering model: {model_name}")

    try:
        register_classes(
            model_name,
            BLACS_tab='user_devices.HV_stahl.BLACS_tabs.HV_Tab',
            runviewer_parser=None,
        )
    except Exception as e:
        logger.error(f"Error registering {model_name}: {e}")