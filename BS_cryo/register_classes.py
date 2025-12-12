from labscript_devices import register_classes

register_classes(
    "BS_cryo",
    BLACS_tab="user_devices.BS_cryo.blacs_tabs.BS_Tab",
    runviewer_parser=None,
)