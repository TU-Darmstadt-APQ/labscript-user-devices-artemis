"""
This file provides a GUI-based visualization for a single-shot scanning process.
It reads the experiment HDF5 file, extracts picoscope traces, camera images, and shot status (camera or power supply failures).

- Plot picoscope traces with trigger markers.
- Display camera images captured during the shot.
- Display the status of the shot, including camera failures and power supply failures.
"""

import numpy as np
import pyqtgraph as pg
from qtutils.qt import QtWidgets, QtGui, QtCore
from pylab import *
from lyse import *
import h5py
from dataclasses import dataclass, field

@dataclass
class ImageData:
    data: np.ndarray
    title: str

@dataclass
class TraceData:
    name: str
    t: np.ndarray
    channels: dict
    triggered_at: int

@dataclass
class CameraFailure:
    orientation: str
    reason: str  # "failed_shot" / "no_images"

@dataclass
class SupplyFailure:
    device: str
    channel: int
    desired: float
    actual: float

@dataclass
class ShotStatus:
    camera_failures: list[CameraFailure] = field(default_factory=list) #callable zero-argument
    supply_failures: list[SupplyFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.camera_failures and not self.supply_failures

parent = QtWidgets.QApplication.activeWindow()
run = Run(path)

############# Globals ###############
globals_dict = run.get_globals()
print("Globals:", globals_dict)

class ShotReader:
    """ Abstract the shot reading methods from GUI visualization. """
    def __init__(self, shot):
        self.shot = shot

    def read_images(self) -> list[ImageData]:
        """
        Gets the images from shot h5 file.
        If no images return empty list.
        :return: List of images
        """
        images = []
        try:
            labels = self.shot.get_all_image_labels()
        except KeyError:
            return images

        for orient, labs in labels.items():
            for label in labs:
                group = self.shot.h5_file[f'images/{orient}/{label}']
                for name in group:
                    img = self.shot.get_image(orient, label, name)
                    images.append(
                        ImageData(
                            data=img,
                            title=f"{orient}/{label}/{name}"
                        )
                    )
        return images

    def read_traces(self) -> list[TraceData]:
        traces = []
        for scope in self.shot.trace_names():
            ds = self.shot.h5_file['data/traces'][scope]
            data = ds[()]
            dt = ds.attrs['sample_interval']
            trig = ds.attrs['triggered_at']
            names = ds.attrs['channel_names']

            t = np.arange(len(data)) * dt
            channels = {n: data[:, i] for i, n in enumerate(names)}

            traces.append(
                TraceData(scope, t, channels, trig)
            )
        return traces

    def read_status(self) -> ShotStatus:
        status = ShotStatus()

        # Camera failures
        try:
            labels = self.shot.get_all_image_labels()
            if not labels:
                status.camera_failures.append(
                    CameraFailure("ALL", "no_images")
                )

            for orient in labels:
                attrs = self.shot.get_attrs(f'images/{orient}')
                if attrs.get("failed_shot", False):
                    status.camera_failures.append(
                        CameraFailure(orient, "failed_shot")
                    )
        except KeyError:
            status.camera_failures.append(
                CameraFailure("ALL", "no_image_group")
            )

        # supply failures
        devices = self.shot.h5_file.get("devices", {})
        for dev_name, dev_grp in devices.items():
            attrs = dev_grp.attrs
            if not attrs.get("failed_set", False):
                continue

            for ch, desired, actual in attrs.get("soft_failed_channels", []):
                status.supply_failures.append(
                    SupplyFailure(
                        device=dev_name,
                        channel=int(ch),
                        desired=float(desired),
                        actual=float(actual),
                    )
                )

            for ch, desired, actual in attrs.get("hard_failed_channels", []):
                status.supply_failures.append(
                    SupplyFailure(
                        device=dev_name,
                        channel=int(ch),
                        desired=float(desired),
                        actual=float(actual),
                    )
                )

        return status


class TraceWindow(pg.GraphicsLayoutWidget):
    def __init__(self, traces: list[TraceData]):
        super().__init__(title="Picoscope traces")
        self._build(traces)

    def _build(self, traces):
        for row, trace in enumerate(traces):
            p = self.addPlot(row=row, col=0, title=trace.name)
            p.addLegend()
            p.showGrid(x=True, y=True)

            for i, (name, y) in enumerate(trace.channels.items()):
                p.plot(trace.t, y, pen=pg.intColor(i), name=name)
                if i == 0:
                    p.plot(
                        [trace.t[trace.triggered_at]],
                        [y[trace.triggered_at]],
                        pen=None,
                        symbol='o',
                        symbolBrush='r'
                    )

class ImagesWindow(QtWidgets.QWidget):
    def __init__(self, images: list[ImageData]):
        super().__init__()
        parent = None

        image_views = []
        for img in images:
            image_view = pg.ImageView(parent=parent)
            image_view.setImage(img.data.swapaxes(-1, -2), autoRange=False, autoLevels=False)
            image_view.setWindowTitle(img.title)
            image_views.append(image_view)

        img_container = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(img_container)

        cols = 3
        for i, img_view in enumerate(image_views):
            r, c = divmod(i, cols)
            grid.addWidget(img_view, r, c)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(img_container)
        scroll.setWidgetResizable(True)

        layout.addWidget(scroll)

class StatusWindow(QtWidgets.QWidget):
    def __init__(self, status: ShotStatus):
        super().__init__()
        self.setWindowTitle("Shot status")

        layout = QtWidgets.QVBoxLayout(self)
        view = QtWidgets.QTextEdit()
        view.setReadOnly(True)
        layout.addWidget(view)

        view.setText(self._format(status))

    def _format(self, status: ShotStatus) -> str:
        lines = []

        if status.ok:
            lines.append("SHOT OK")
            return "\n".join(lines)

        lines.append("SHOT FAILED\n")

        if status.camera_failures:
            lines.append("Camera failures:")
            for f in status.camera_failures:
                lines.append(
                    f"  - {f.orientation}: {f.reason}"
                )
            lines.append("")

        if status.supply_failures:
            lines.append("Power supply failures (target -> monitored):")
            for f in status.supply_failures:
                lines.append(
                    f"  - {f.device} ch {f.channel}: "
                    f"{f.desired:.1f} V --> {f.actual:.1f} V"
                )

        return "\n".join(lines)

def tile_windows(windows, cols=3, margin=20):
    screen = QtGui.QGuiApplication.primaryScreen()
    geo = screen.availableGeometry()

    rows = int(np.ceil(len(windows) / cols))
    w = (geo.width() - margin * (cols + 1)) // cols
    h = (geo.height() - margin * (rows + 1)) // rows

    for i, win in enumerate(windows):
        r, c = divmod(i, cols)
        win.resize(w, h)
        win.move(
            geo.left() + margin + c * (w + margin),
            geo.top() + margin + r * (h + margin)
        )
        win.show()

########################## READ DATA FROM H5 ############################
with Run(path).open('r') as shot:
    reader = ShotReader(shot)

    images = reader.read_images()
    traces = reader.read_traces()
    status = reader.read_status()
########################## READ DATA FROM H5 ############################

main_win = QtWidgets.QMainWindow()
main_win.setWindowTitle("Shot diagnostics")
main_win.resize(1400, 900)
main_win.setWindowFlags(QtCore.Qt.Tool)
main_win.setAttribute(QtCore.Qt.WA_DeleteOnClose)

# place main window
screen = QtGui.QGuiApplication.primaryScreen()
geo = screen.availableGeometry()
main_win.move(
    geo.left() + 200,
    geo.top()
)
# central widget + layout
central = QtWidgets.QWidget()
main_win.setCentralWidget(central)

layout = QtWidgets.QVBoxLayout(central)

# vertical splitter
splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
layout.addWidget(splitter)

# --- Trace Window ---
if traces:
    trace_win = TraceWindow(traces)
    trace_win.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    splitter.addWidget(trace_win)

# --- Images Window ---
if images:
    images_win = ImagesWindow(images)
    images_win.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    splitter.addWidget(images_win)

# --- Status Window ---
status_win = StatusWindow(status)
status_win.setMaximumHeight(200)
status_win.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
splitter.addWidget(status_win)

splitter.setStretchFactor(0, 3)
splitter.setStretchFactor(1, 4)
splitter.setStretchFactor(2, 1)

main_win.show()