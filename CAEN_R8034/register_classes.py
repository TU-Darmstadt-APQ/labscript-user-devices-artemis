from labscript_devices import register_classes

register_classes(
    "CAEN",
    BLACS_tab='user_devices.CAEN_R8034.BLACS_tabs.CAENTab',
    runviewer_parser=None,
)