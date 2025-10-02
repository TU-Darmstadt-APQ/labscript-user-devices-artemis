from blacs.tab_base_classes import Worker
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger
from blacs.tab_base_classes import MODE_MANUAL
from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget
)

class PicoScopeTab(DeviceTab):
    def initialise_GUI(self):
        # Get properties from connection table
        connection_table = self.settings['connection_table']
        device = connection_table.find_by_name(self.device_name)
        properties = device.properties

        layout = self.get_tab_layout()
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 1. Channels
        channels_configs = [input.properties['channel_config'] for input in device.child_list.values()]

        channels_tab = QWidget()
        channels_layout = QVBoxLayout(channels_tab)
        channels_layout.addWidget(self.make_table(
            "Channels",
            ["Channel", "Name", "Enabled", "Coupling", "Range", "Analog Offset"],
            channels_configs
        ))
        self.tabs.addTab(channels_tab, "Channels")

        # 2. Trigger
        trigger_tab = QWidget()
        trigger_layout = QVBoxLayout(trigger_tab)

        trigger_conditions = properties.get("trigger_conditions_config", [])
        if trigger_conditions:
            trigger_layout.addWidget(self.make_table("Trigger Conditions",
                                                     ["Sources", "Info"], trigger_conditions))

        trigger_directions = properties.get("trigger_directions_config", [])
        if trigger_directions:
            trigger_layout.addWidget(self.make_table("Trigger Directions",
                                                     ["Source", "Direction"],trigger_directions))

        trigger_properties = properties.get("trigger_properties_config", [])
        if trigger_properties:
            trigger_layout.addWidget(self.make_table(
                "Trigger Properties",
                ["Source", "Threshold Upper", "Threshold Lower", "Upper Hysteresis", "Lower Hysteresis","Threshold Mode"],
                trigger_properties
            ))

        trigger_delay = properties.get("trigger_delay_config", {})
        if trigger_delay:
            trigger_layout.addWidget(self.make_table("Trigger Delay", ["Parameter", "Value"], trigger_delay))

        simple_trigger = properties.get("simple_trigger_config", {})
        if simple_trigger:
            trigger_layout.addWidget(self.make_table("Simple Trigger", ["Parameter", "Value"], simple_trigger))

        self.tabs.addTab(trigger_tab, "Trigger")

        # 3. Sampling
        sampling_tab = QWidget()
        sampling_layout = QVBoxLayout(sampling_tab)

        block_config = properties.get("block_config", {})
        if block_config:
            sampling_layout.addWidget(self.make_table("Block Config", ["Parameter", "Value"], block_config))

        rapid_block_config = properties.get("rapid_block_config", {})
        if rapid_block_config:
            sampling_layout.addWidget(self.make_table("Rapid Block Config", ["Parameter", "Value"], rapid_block_config))

        stream_config = properties.get("stream_config", {})
        if stream_config:
            sampling_layout.addWidget(self.make_table("Stream Config", ["Parameter", "Value"], stream_config))

        self.tabs.addTab(sampling_tab, "Sampling")

        # 4. SigGen
        siggen_tab = QWidget()
        siggen_layout = QVBoxLayout(siggen_tab)

        siggen_config = properties.get("siggen_config", {})
        if siggen_config:
            siggen_layout.addWidget(self.make_table("SigGen Config", ["Parameter", "Value"], siggen_config))

        self.tabs.addTab(siggen_tab, "SigGen")

        # static button to use in manual mode
        button_layout = QHBoxLayout()
        # todo: add functionality
        self.start_button = QPushButton("Start Block Capture")
        self.stream_button = QPushButton("Start Streaming")
        self.siggen_button = QPushButton("Trigger Signal Generator")
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stream_button)
        button_layout.addWidget(self.siggen_button)
        layout.addLayout(button_layout)

        return

    def initialise_workers(self):
        # Get properties from connection table.
        device = self.settings['connection_table'].find_by_name(self.device_name)

        # look up the serial number
        serial = device.properties["serial_number"]
        no_inputs = device.properties["channels_number"]

        # Start a worker process
        self.create_worker(
            'main_worker',
            'user_devices.PicoScope4000A.blacs_workers.PicoScopeWorker',
            {"serial_number": serial, "no_inputs": no_inputs}  # All connection table properties should be added
        )
        self.primary_worker = "main_worker"

    def make_table(self, title, headers, data):
        """
        todo: add table labels
        data: dict | list[dict] | []
        """
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        if data is None or data == {} or data == []:
            table.setRowCount(0)
            return table

        if isinstance(data, dict):
            # Transform dict into str array: param - value
            table.setRowCount(len(data))
            for row, (k, v) in enumerate(data.items()):
                table.setItem(row, 0, QTableWidgetItem(str(k)))
                table.setItem(row, 1, QTableWidgetItem(str(v)))
        elif isinstance(data, list):
            table.setRowCount(len(data))
            for row, entry in enumerate(data):
                for col, key in enumerate(headers):
                    val = entry.get(key.lower().replace(" ", "_"), "")
                    table.setItem(row, col, QTableWidgetItem(str(val)))
        else:
            logger.warning(f"Unsupported data type for table {title}: {type(data)}")

        return table

