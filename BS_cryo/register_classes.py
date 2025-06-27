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
    "BS_cryo",
    BLACS_tab='user_devices.BS_cryo.BLACS_tabs.BS_cryoTab',
    runviewer_parser=None,
)

for model_name in capabilities:
    logger.debug(f"[BS_cryo] Registering model: {model_name}")

    try:
        register_classes(
            model_name,
            BLACS_tab='user_devices.BS_cryo.BLACS_tabs.BS_cryoTab',
            runviewer_parser=None,
        )
    except Exception as e:
        logger.error(f"[BS_cryo] Error registering {model_name}: {e}")