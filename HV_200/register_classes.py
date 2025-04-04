from labscript_devices import register_classes

register_classes(
    "HV_200",
    BLACS_tab='user_devices.HV_200.BLACS_tabs.HV_200Tab',
    runviewer_parser=None,
)