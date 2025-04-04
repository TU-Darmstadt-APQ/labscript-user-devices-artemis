from labscript_devices import register_classes

register_classes(
    "BS_110",
    BLACS_tab='user_devices.BS_110.BLACS_tabs.BS110Tab',
    runviewer_parser=None,
)