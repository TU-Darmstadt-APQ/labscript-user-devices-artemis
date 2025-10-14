from labscript_devices import register_classes

register_classes(
    "AlviumCamera",
    BLACS_tab='user_devices.AlliedVision.blacs_tabs.CameraTab',
    runviewer_parser=None,
)