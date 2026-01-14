# ~/labscript-suite/userlib/analysislib/example_apparatus/multi_shot_lyse_scan.py
from lyse import *
from pylab import *
import pyqtgraph as pg
from qtutils.qt import QtWidgets, QtGui, QtCore


df = data()
shots_data = []

for path in df['filepath']:
    run = Run(path)
    globals_dict = run.get_globals()

    images = []
    titles = []
    try:
        image_labels_dict = run.get_all_image_labels()
    except KeyError:
        image_labels_dict = {}

    with run.open('r') as shot:
        for orientation, labels in image_labels_dict.items():
            for label in labels:
                group = shot.h5_file[f'images/{orientation}/{label}']
                for image_name in group.keys():
                    images.append(shot.get_image(orientation, label, image_name))
                    titles.append(f"{orientation}/{label}/{image_name}")

        traces = {}
        for picoscope in shot.trace_names():
            traces_ds = shot.h5_file['data']['traces'][picoscope]
            traces_names = traces_ds.attrs["channel_names"]
            data_array = traces_ds[()]
            traces[picoscope] = {name: data_array[:, i] for i, name in enumerate(traces_names)}

    shots_data.append({
        'path': path,
        'globals': globals_dict,
        'images': images,
        'titles': titles,
        'traces': traces
    })


window = QtWidgets.QWidget()
window.setWindowFlags(QtCore.Qt.Tool)
window.setAttribute(QtCore.Qt.WA_DeleteOnClose)
layout = QtWidgets.QVBoxLayout(window)

scroll = QtWidgets.QScrollArea()
scroll.setWidgetResizable(True)
scroll_content = QtWidgets.QWidget()
scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
scroll_content.setLayout(scroll_layout)
scroll.setWidget(scroll_content)
layout.addWidget(scroll)

for shot in shots_data:
    row_widget = QtWidgets.QWidget()
    row_layout = QtWidgets.QHBoxLayout()
    row_widget.setLayout(row_layout)

    # Globals as labels
    # globals_text = "\n".join(f"{k}: {v}" for k, v in shot['globals'].items())
    # row_layout.addWidget(QtWidgets.QLabel(globals_text))

    globals_text = "\n".join(f"{k}: {v}" for k, v in shot['globals'].items())
    globals_label = QtWidgets.QLabel(globals_text)
    globals_label.setFixedWidth(150)
    row_layout.addWidget(globals_label)

    # Traces
    #todo: add trigger point
    trace_plot = pg.PlotWidget()
    trace_plot.addLegend()
    trace_plot.setMinimumWidth(400)
    for picoscope, tdict in shot['traces'].items():
        for name, y in tdict.items():
            x = np.arange(len(y))
            color_idx = abs(hash(name)) % 256
            trace_plot.plot(x, y, pen=pg.intColor(color_idx), name=name)
    row_layout.addWidget(trace_plot, stretch=1)

    # Display first image (or multiple if you want)
    if shot['images']:
        tabs = QtWidgets.QTabWidget()
        tabs.setMinimumWidth(300)
        for i, img in enumerate(shot['images']):
            img_view = pg.ImageView()
            img_view.setImage(img.swapaxes(-1, -2), autoRange=False, autoLevels=False)
            tabs.addTab(img_view, shot['titles'][i])
        row_layout.addWidget(tabs)

    scroll_layout.addWidget(row_widget)
    # layout.addWidget(row_widget)

scroll_layout.addStretch()
window.show()