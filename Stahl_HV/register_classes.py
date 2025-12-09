from labscript_devices import register_classes

register_classes(
    "Stahl_HV",
    BLACS_tab="user_devices.Stahl_HV.BLACS_tabs.HV_Tab",
    runviewer_parser=None,
)