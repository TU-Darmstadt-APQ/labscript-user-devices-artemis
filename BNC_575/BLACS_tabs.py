from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger
from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import *
from qtutils.qt.QtWidgets import QPushButton, QSizePolicy as QSP, QHBoxLayout, QSpacerItem
from blacs.tab_base_classes import MODE_MANUAL
from user_devices.BNC_575.pulse_gen_widgets import ChannelWidget, SystemWidget
from labscript_utils.qtwidgets.toolpalette import ToolPaletteGroup


class BNC_575Tab(DeviceTab):
    def initialise_GUI(self):
        layout = QVBoxLayout()
        self.get_tab_layout().addLayout(layout)

        # System config
        self.system_box = QGroupBox("System Configuration")
        sys_layout = QVBoxLayout()
        sys_layout.addWidget(SystemWidget('system'))
        self.system_box.setLayout(sys_layout)
        layout.addWidget(self.system_box)

        # Channel config
        self.channels_box = QGroupBox("Channels")
        ch_layout = QGridLayout()
        self.channel_widgets = []
        rows = 4
        cols = 2
        conn_names = self.get_channel_names()

        for i in range(8):
            hw_name = f"pulse {i+1}"
            conn_name = conn_names.get(hw_name, '-')
            ch = ChannelWidget(f"pulse {i+1}", connection_name=conn_name)
            row = i // cols
            col = i % cols
            ch_layout.addWidget(ch, row, col)
            self.channel_widgets.append(ch)

        self.channels_box.setLayout(ch_layout)
        layout.addWidget(self.channels_box)

        # Buttons
        self.create_control_buttons()

        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)

    def initialise_workers(self):
        connection_table = self.settings['connection_table']
        device_properties = connection_table.find_by_name(self.device_name).properties # dict
        channels_properties = self.get_children_properties()

        worker_kwargs = {
            "name": self.device_name + '_main',
            "device_properties": device_properties,
            "channels_properties": channels_properties
        }

        self.create_worker(
            'main_worker',
            'user_devices.BNC_575.BLACS_workers.BNC_575Worker',
            worker_kwargs,
        )

        self.primary_worker = "main_worker"

    def get_children_properties(self):
        children_properties = []
        connection_table = self.settings['connection_table']
        device = connection_table.find_by_name(self.device_name)

        for i in range(len(device.child_list)):
            child = self.get_child_from_connection_table(self.device_name, 'pulse {:01d}'.format(i + 1))
            children_properties.append(child.properties)

        return children_properties

    def get_channel_names(self):
        names = {}
        children_properties = self.get_children_properties()

        for child in children_properties:
            name = child.get('name')
            if name:
                names[child.get('connection')] = name
        return names

    def create_control_buttons(self):
        # Create buttons
        self.btn_configure = QPushButton()
        self.btn_trigger = QPushButton()
        self.btn_reset = QPushButton()

        #
        style = QApplication.style()
        reset_icon = style.standardIcon(QStyle.SP_DialogResetButton)
        configure_icon = style.standardIcon(QStyle.SP_DialogOkButton)
        trigger_icon = style.standardIcon(QStyle.SP_TitleBarShadeButton)
        self.btn_configure.setIcon(configure_icon)
        self.btn_trigger.setIcon(trigger_icon)
        self.btn_reset.setIcon(reset_icon)

        # Tooltip for clarity (optional)
        self.btn_configure.setToolTip("Configure")
        self.btn_trigger.setToolTip("Trigger")
        self.btn_reset.setToolTip("Reset")

        # Uniform style
        for btn in [self.btn_configure, self.btn_trigger, self.btn_reset]:
            btn.setFixedSize(30, 30)
            btn.setIconSize(QSize(16, 16))
            btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid #B8B8B8;
                    border-radius: 4px;
                    background-color: #F0F0F0;
                    padding: 4px;
                }
                QPushButton:hover {
                    background-color: #E0E0E0;
                }
                QPushButton:pressed {
                    background-color: #D0D0D0;
                }
            """)

        # Layout
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(5)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_configure)
        button_layout.addWidget(self.btn_trigger)
        button_layout.addWidget(self.btn_reset)

        container = QWidget()
        container.setLayout(button_layout)

        # Add to top of main tab layout
        self.get_tab_layout().insertWidget(0, container)

        # Connect signals
        self.btn_configure.clicked.connect(self.configure_device)
        self.btn_trigger.clicked.connect(self.trigger_device)
        self.btn_reset.clicked.connect(self.reset_device)

    @define_state(MODE_MANUAL, True)
    def trigger_device(self, checked=None):
        try:
            yield (self.queue_work(self.primary_worker, 'trigger', []))
        except Exception as e:
            logger.debug(f"[BNC] Error by send work to worker(trigger): \t {e}")

    @define_state(MODE_MANUAL, True)
    def configure_device(self, checked=None):
        logger.info(f"ALL i Want Is to Configure the device with values from widgets/ huh")

        # Get system configuration
        try:
            system_config = self.system_box.findChild(SystemWidget).get_config()
            logger.debug(f"system congif: {system_config}")
        except Exception as e:
            logger.warning(f"Failed to get system config: {e}")
            system_config = {}

        # Get channels configuration
        channels_config = []
        for idx, ch_widget in enumerate(self.channel_widgets):
            try:
                config = ch_widget.get_config()
                logger.debug(f"channel config: {config}")
                channels_config.append(config)
            except Exception as e:
                logger.warning(f"Failed to get config from {ch_widget._hardware_name}: {e}")
                config = {}

        logger.debug(f"CHANNELSS config: {channels_config}")

        try:
            yield (self.queue_work(self.primary_worker, 'configure', [system_config, channels_config]))
        except Exception as e:
            logger.debug(f"[BNC] Error by send work to worker(configure): \t {e}")

    def reset_device(self):
        # logger.info(
        #     "Now we want to reset the device AND the widgets to their default values. What are they? We don't know. / huh")
        try:
            yield (self.queue_work(self.primary_worker, 'reset', []))
        except Exception as e:
            logger.debug(f"[BNC] Error by send work to worker(reset): \t {e}")