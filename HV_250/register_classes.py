from labscript_devices import register_classes

register_classes(
    "HV_250",
    BLACS_tab='user_devices.HV_250.BLACS_tabs.HV_250Tab',
    runviewer_parser=None,
)