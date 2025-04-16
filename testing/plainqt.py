import sys
from PyQt5.QtWidgets import QApplication, QPushButton

app = QApplication(sys.argv)
button = QPushButton("Привет! Нажми меня")
button.resize(300, 100)
button.show()
sys.exit(app.exec_())