from labscript_devices import register_classes

register_classes(
    "BNC_575",
    BLACS_tab='user_devices.BNC_575.BLACS_tabs.BNC_575Tab',
    runviewer_parser=None,
)