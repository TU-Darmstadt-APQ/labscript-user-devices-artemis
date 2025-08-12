from labscript_devices import register_classes

register_classes(
    "IDSCamera",
    BLACS_tab='user_devices.ids_camera.BLACS_tabs.CameraTab',
    runviewer_parser=None,
)