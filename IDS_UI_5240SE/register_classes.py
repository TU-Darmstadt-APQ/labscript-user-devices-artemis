from labscript_devices import register_classes

register_classes(
    "IDS_UICamera",
    BLACS_tab='user_devices.IDS_UI_5240SE.blacs_tabs.IDSCameraTab',
    runviewer_parser=None,
)