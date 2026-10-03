import mss
import mss.tools
import cv2
import numpy as np

class ScreenCapture:
    def __init__(self):
        self.sct = mss.mss()

    def capture_region(self, bbox):
        """
        Captures a specific region of the screen.
        :param bbox: A dictionary with 'top', 'left', 'width', 'height'
                     or a tuple (left, top, right, bottom)
        :return: numpy array of the image (BGR format for OpenCV)
        """
        if isinstance(bbox, tuple) and len(bbox) == 4:
            monitor = {"top": bbox[1], "left": bbox[0], "width": bbox[2]-bbox[0], "height": bbox[3]-bbox[1]}
        elif isinstance(bbox, dict):
            monitor = bbox
        else:
            raise ValueError("Invalid bbox format. Use dict or tuple.")
        
        sct_img = self.sct.grab(monitor)
        # Convert to numpy array
        img = np.array(sct_img)
        # Drop alpha channel
        return img[:, :, :3]

    def capture_full(self):
        """
        Captures the primary monitor.
        :return: numpy array of the full screen image
        """
        monitor = self.sct.monitors[1]
        sct_img = self.sct.grab(monitor)
        img = np.array(sct_img)
        return img[:, :, :3]

    def close(self):
        self.sct.close()

if __name__ == "__main__":
    # Test script
    capturer = ScreenCapture()
    img = capturer.capture_full()
    print(f"Captured full screen with shape {img.shape}")
    capturer.close()
