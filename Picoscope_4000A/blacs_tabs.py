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
import h5py
import labscript_utils.properties


CONNECTIONS = {
    "channel_A": 0,
    "channel_B": 1,
    "channel_C": 2,
    "channel_D": 3,
    "channel_E": 4,
    "channel_F": 5,
    "channel_G": 6,
    "channel_H": 7,
}

COLORS = [(102, 0, 204),  # purple
          (0, 0, 204),  # blue
          (0, 204, 204),  # cian
          (102, 240, 0),  # green
          (204, 204, 0),  # yellow
          (204, 0, 0),  # red
          (255, 51, 255),  # pink
          (96, 96, 96)]  # gray

class TraceReceiver(ZMQServer):

    def __init__(self, trace_view):
        """
        :param channel_names: (dict) trace_idx<int>: ch_name<str>
        """
        ZMQServer.__init__(self, port=None, dtype='multipart')
        self.trace_view = trace_view

    @inmain_decorator(wait_for_return=True)
    def handler(self, data):
        self.send([b'ok'])
        md = json.loads(data[0])
        traces = np.frombuffer(memoryview(data[1]), dtype=md['dtype'])
        traces = traces.reshape(md['shape'])

        sample_interval = md['sample_interval']
        triggered_at = md['triggered_at']
        total_samples = md['shape'][0]
        channel_names = md['channel_names']

        times = np.linspace(0, (total_samples - 1) * sample_interval, total_samples)

        self.trace_view.clear()

        # plot traces

        for col_idx, name in channel_names.items():
            self.plot_line(name, times, traces[:, col_idx], col_idx)

        # plot trigger dot
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
        if isinstance(color, int):
            pen = pg.intColor(color)
        else:
            pen = pg.mkPen(color=color, width=1)
        self.trace_view.plot(
            time,
            trace,
            name=name,
            pen=pen,
        )

class PicoScopeTab(DeviceTab):
    def initialise_GUI(self):

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

        self.trace_receiver = TraceReceiver(trace_view=self.trace_graph)
        return

    def initialise_workers(self):
        # get properties
        table = self.settings['connection_table']
        connection_table_properties = table.find_by_name(self.device_name).properties
        with h5py.File(table.filepath, 'r') as f:
            device_properties = labscript_utils.properties.get(
                f, self.device_name, "device_properties"
            )

        worker_kwargs = {
            'serial_number': connection_table_properties['serial_number'],
            'is_4000a': connection_table_properties['is_4000a'],
            'simple_trigger': device_properties['simple_trigger_config'],
            'stream_config': device_properties['stream_config'],
            'block_config': device_properties['block_config'],
            'image_receiver_port': self.trace_receiver.port,
            'channels_properties': device_properties['channels_properties'],
        }

        # Start a worker process
        self.create_worker(
            'main_worker',
            'user_devices.Picoscope_4000A.blacs_workers.PicoScopeWorker',
            worker_kwargs,
        )
        self.primary_worker = "main_worker"