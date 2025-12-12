from labscript_devices import register_classes

register_classes(
    "PicoScope4000A",
    BLACS_tab='user_devices.PicoScope4000A.blacs_tabs.PicoScopeTab',
    runviewer_parser=None,
)