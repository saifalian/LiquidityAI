import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.current_prediction = {"direction": "NEUTRAL", "confidence": 0, "reason": "Connecting..."}
        
    def initUI(self):
        # Frameless window, transparent background, always on top
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Position top left inside common browser space
        self.setGeometry(100, 100, 500, 150)
        
        layout = QVBoxLayout()
        self.label_dir = QLabel("NEUTRAL", self)
        self.label_dir.setFont(QFont('Arial', 32, QFont.Bold))
        self.label_dir.setStyleSheet("color: white; background-color: rgba(0,0,0,150); padding: 10px; border-radius: 5px;")
        
        self.label_details = QLabel("Initializing engine...", self)
        self.label_details.setFont(QFont('Arial', 14))
        self.label_details.setStyleSheet("color: white; background-color: rgba(0,0,0,150); padding: 5px; border-radius: 5px;")
        
        layout.addWidget(self.label_dir)
        layout.addWidget(self.label_details)
        layout.setAlignment(Qt.AlignTop)
        
        self.setLayout(layout)
        
        # Timer to update UI
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(500)

    def set_prediction(self, prediction_dict):
        self.current_prediction = prediction_dict
        
    def update_display(self):
        d = self.current_prediction.get("direction", "NEUTRAL")
        c = self.current_prediction.get("confidence", 0)
        r = self.current_prediction.get("reason", "")
        
        color = "white"
        if d == "UP": color = "#00FF00" # Lime
        elif d == "DOWN": color = "#FF0000" # Red
        
        self.label_dir.setText(f"{d} ({c:.2f})")
        self.label_dir.setStyleSheet(f"color: {color}; background-color: rgba(0,0,0,150); padding: 10px; border-radius: 5px;")
        self.label_details.setText(r)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = OverlayWindow()
    ex.show()
    sys.exit(app.exec_())
