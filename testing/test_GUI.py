from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import *
from qtutils.qt.QtWidgets import QApplication, QPushButton

from qtutils import *
import qtutils.icons

import sys

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("UI wighout Qt Designer")
        self.setGeometry(100, 100, 400, 200)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.button = QPushButton("Press")
        self.button.clicked.connect(self.on_button_click)

        layout = QVBoxLayout()
        layout.addWidget(self.button)

        central_widget.setLayout(layout)

    def on_button_click(self):
        QMessageBox.information(self, "Привет!", "Кнопка нажата!")

# ЗLaunch app
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())