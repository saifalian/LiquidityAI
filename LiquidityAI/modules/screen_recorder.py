from PyQt5.QtCore import QThread, pyqtSignal
import cv2
import numpy as np
from datetime import datetime
import time
import os

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False


class ScreenRecorderWorker(QThread):
    recording_stopped = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_recording = False

    def run(self):
        if not HAS_MSS:
            print("Screen recorder: 'mss' library not installed. Run: pip install mss")
            self.recording_stopped.emit()
            return

        self.is_recording = True

        try:
            # mss must be created inside the thread
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # primary monitor
                width  = monitor["width"]
                height = monitor["height"]

                # Save into project folder
                folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                filename = os.path.join(
                    folder,
                    f"Session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.avi"
                )
                print(f"[Recorder] Starting: {filename}  ({width}x{height} @ 10 fps)")

                fourcc = cv2.VideoWriter_fourcc(*'XVID')
                out = cv2.VideoWriter(filename, fourcc, 10.0, (width, height))

                while self.is_recording:
                    try:
                        img   = sct.grab(monitor)
                        frame = np.array(img)
                        # BGRA -> BGR  (correct constant name)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        out.write(frame)
                        time.sleep(0.1)   # ~10 FPS
                    except Exception as e:
                        print(f"[Recorder] Frame error: {e}")
                        self.is_recording = False

                out.release()
                print(f"[Recorder] Saved: {filename}")

        except Exception as e:
            print(f"[Recorder] Fatal error: {e}")

        self.recording_stopped.emit()

    def stop_recording(self):
        self.is_recording = False
