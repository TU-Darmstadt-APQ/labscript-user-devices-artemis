from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger
from blacs.tab_base_classes import MODE_MANUAL
from labscript_utils.ls_zprocess import ZMQServer
from qtutils.qt import QtWidgets, QtGui, QtCore

from qtutils.qt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget
)
from labscript_utils.ls_zprocess import ZMQServer
from qtutils import inmain_decorator
import pyqtgraph as pg
import json
import numpy as np


class TraceReceiver(ZMQServer):

    def __init__(self, trace_view, total_samples, channel_names):
        ZMQServer.__init__(self, port=None, dtype='multipart')
        self.trace_view = trace_view
        self.total_samples = total_samples
        self.channel_names = channel_names

    @inmain_decorator(wait_for_return=True)
    def handler(self, data):
        self.send([b'ok'])
        md = json.loads(data[0])
        traces = np.frombuffer(memoryview(data[1]), dtype=md['dtype'])
        traces = traces.reshape(md['shape'])
        sample_interval = md['sample_interval']
        triggered_at = md['triggered_at']
        times = np.linspace(0, (self.total_samples - 1) * sample_interval, self.total_samples)

        colors = [(102, 0, 204), # purple
                  (0, 0, 204), # blue
                  (0, 204, 204), # cian
                  (102, 240, 0), # green
                  (204, 204, 0), # yellow
                  (204, 0, 0), # red
                  (255, 51, 255), # pink
                  (96, 96, 96)] # gray

        self.trace_view.clear()

        for i in range(len(self.channel_names)):
            self.plot_line(self.channel_names[i], times, traces[:,i], colors[i])

        self.trace_view.addLine(x=triggered_at * sample_interval, y=traces[triggered_at:1], pen=pg.mkPen(color='r', width=1.5, style=QtCore.Qt.DashLine)) # endless vertical line where the trigger occurred.
        self.plot_dot_trigger(x=triggered_at * sample_interval, y=traces[triggered_at, 0]) # NOTE: Dot on first channel A

        QtWidgets.QApplication.instance().sendPostedEvents()
        return self.NO_RESPONSE

    def plot_dot_trigger(self, x, y):
        """Plots the dot where trigger occurred only on single given channel  """
        self.trace_view.plot(
            [x],
            [y],
            symbol='o',
            symbolSize=6.5,
            symbolBrush='r',
            symbolPen=None,
            pen=None
        )

    def plot_line(self, name, time, trace, color):
        pen = pg.mkPen(color=color, width=1)
        self.trace_view.plot(
            time,
            trace,
            name=name,
            pen=pen,
        )


class PicoScopeTab(DeviceTab):
    def initialise_GUI(self):
        # Get properties from connection table
        connection_table = self.settings['connection_table']
        device = connection_table.find_by_name(self.device_name)
        properties = device.properties
        self.worker_kwargs = {}

        layout = self.get_tab_layout()

        # 0. Traces
        self.trace_graph = pg.PlotWidget()
        self.trace_graph.setBackground('w')
        self.trace_graph.setLabel("left", "Voltages (mV)")
        self.trace_graph.setLabel("bottom", "Time (ns)")
        self.trace_graph.showGrid(x=True, y=True)
        self.trace_graph.addLegend()
        layout.addWidget(self.trace_graph, stretch=1)

        self.tabs_window = QtWidgets.QMainWindow()
        self.tabs_window.setWindowTitle("Tabs")
        self.tabs = QTabWidget()
        self.tabs_window.setCentralWidget(self.tabs)
        self.tabs_window.resize(400, 300)
        # layout.addWidget(self.tabs, stretch=0)

        # 1. Channels
        channels_configs = [input.properties['channel_config'] for input in device.child_list.values()]
        self.channel_names = [ch['name'] for ch in channels_configs]

        channels_tab = QWidget()
        channels_layout = QVBoxLayout(channels_tab)
        channels_layout.addWidget(self.make_table(
            "Channels",
            ["Channel", "Name", "Enabled", "Coupling", "Range", "Analog Offset"],
            channels_configs
        ))
        self.worker_kwargs["channels_configs"] = channels_configs
        self.tabs.addTab(channels_tab, "Channels")

        # 2. Trigger
        trigger_tab = QWidget()
        trigger_layout = QVBoxLayout(trigger_tab)

        trigger_conditions = properties.get("trigger_conditions_config", [])
        if trigger_conditions:
            trigger_layout.addWidget(self.make_table("Trigger Conditions",
                                                     ["Sources", "Info"], trigger_conditions))
            self.worker_kwargs["trigger_conditions"] = trigger_conditions

        trigger_directions = properties.get("trigger_directions_config", [])
        if trigger_directions:
            trigger_layout.addWidget(self.make_table("Trigger Directions",
                                                     ["Source", "Direction"],trigger_directions))
            self.worker_kwargs["trigger_directions"] = trigger_directions

        trigger_properties = properties.get("trigger_properties_config", [])
        if trigger_properties:
            trigger_layout.addWidget(self.make_table(
                "Trigger Properties",
                ["Source", "Threshold Upper", "Threshold Lower", "Upper Hysteresis", "Lower Hysteresis","Threshold Mode"],
                trigger_properties
            ))
            self.worker_kwargs["trigger_properties"] = trigger_properties

        trigger_delay = properties.get("trigger_delay_config", {})
        if trigger_delay:
            trigger_layout.addWidget(self.make_table("Trigger Delay", ["Parameter", "Value"], trigger_delay))
            self.worker_kwargs["trigger_delay"] = trigger_delay

        simple_trigger = properties.get("simple_trigger_config", {})
        if simple_trigger:
            trigger_layout.addWidget(self.make_table("Simple Trigger", ["Parameter", "Value"], simple_trigger))
            self.worker_kwargs["simple_trigger"] = simple_trigger

        self.tabs.addTab(trigger_tab, "Trigger")

        # 3. Sampling
        sampling_tab = QWidget()
        sampling_layout = QVBoxLayout(sampling_tab)

        stream_config = properties.get("stream_config", {})
        sampling_layout.addWidget(self.make_table("Stream Config", ["Parameter", "Value"], stream_config))
        self.worker_kwargs["stream_config"] = stream_config
        total_samples = stream_config['no_post_trigger_samples']

        self.tabs.addTab(sampling_tab, "Sampling")

        # 4. SigGen
        siggen_tab = QWidget()
        siggen_layout = QVBoxLayout(siggen_tab)

        siggen_config = properties.get("siggen_config", {})
        if siggen_config:
            siggen_layout.addWidget(self.make_table("SigGen Config", ["Parameter", "Value"], siggen_config))
            self.worker_kwargs["siggen_config"] = siggen_config

        self.tabs.addTab(siggen_tab, "SigGen")

        # static button to use in manual mode
        button_layout = QHBoxLayout()

        self.attributes_button = QPushButton("Attributes")
        self.stream_button = QPushButton("Start Streaming") # start streaming in manual mode
        self.siggen_button = QPushButton("Trigger Signal Generator")
        self.attributes_button.clicked.connect(self.open_attributes)
        self.stream_button.clicked.connect(self.start_sampling)
        self.siggen_button.clicked.connect(self.siggen_trigger)

        button_layout.addWidget(self.stream_button)
        button_layout.addWidget(self.siggen_button)
        button_layout.addWidget(self.attributes_button)
        layout.addLayout(button_layout)

        logger.debug(self.worker_kwargs)

        self.trace_receiver = TraceReceiver(trace_view=self.trace_graph, total_samples=total_samples, channel_names=self.channel_names)
        return

    def initialise_workers(self):
        # Get properties from connection table.
        device = self.settings['connection_table'].find_by_name(self.device_name)

        # look up the serial number, series
        serial = device.properties["serial_number"]
        is_4000a = device.properties["is_4000a"]
        # Start a worker process
        self.create_worker(
            'main_worker',
            'user_devices.PicoScope4000A.blacs_workers.PicoScopeWorker',
            {"serial_number": serial,
             "is_4000a": is_4000a,
             "simple_trigger": self.worker_kwargs.get("simple_trigger", {}),
             "channels_configs": self.worker_kwargs.get("channels_configs", []),
             "channel_names": self.channel_names,
             "trigger_conditions": self.worker_kwargs.get("trigger_conditions", []),
             "trigger_directions": self.worker_kwargs.get("trigger_directions", []),
             "trigger_properties": self.worker_kwargs.get("trigger_properties", []),
             "trigger_delay": self.worker_kwargs.get("trigger_delay", {}),
             "stream_config": self.worker_kwargs.get("stream_config", {}),
             "siggen_config": self.worker_kwargs.get("siggen_config", {}),
             "image_receiver_port": self.trace_receiver.port,
             }
        )
        self.primary_worker = "main_worker"

    def make_table(self, title, headers, data):
        """
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

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def siggen_trigger(self, button):
        yield (self.queue_work(self.primary_worker, 'siggen_software_trigger'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def start_sampling(self, button):
        yield (self.queue_work(self.primary_worker, 'start_sampling'))

    def open_attributes(self, button):
        self.tabs_window.show()

