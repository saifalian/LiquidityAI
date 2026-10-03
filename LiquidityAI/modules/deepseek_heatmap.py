import cv2
import numpy as np
import mss
import pyautogui
import pygetwindow as gw
import win32gui
import win32con
import time
import pytesseract
import os

# Set Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class WindowFocus:
    def __init__(self, window_title_substring="Coinglass"):
        self.window_title_substring = window_title_substring
        self.window = None

    def focus_window(self):
        # Find all windows whose title contains the substring
        windows = gw.getWindowsWithTitle(self.window_title_substring)
        if not windows:
            raise Exception(f"No window with title containing '{self.window_title_substring}' found.")
        self.window = windows[0]

        # If minimized, restore it
        if self.window.isMinimized:
            win32gui.ShowWindow(self.window._hWnd, win32con.SW_RESTORE)
        # Bring to foreground
        self.window.activate()
        time.sleep(1)  # Allow time for the window to come forward

class ChartLocator:
    def __init__(self, window_region):
        self.window_region = window_region  # (left, top, width, height)
        self.chart_bbox = None  # (x, y, w, h) relative to screen

    def locate_chart(self):
        # Capture the entire window
        with mss.mss() as sct:
            monitor = {"left": self.window_region[0], "top": self.window_region[1],
                       "width": self.window_region[2], "height": self.window_region[3]}
            img = np.array(sct.grab(monitor))
            img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        # Convert to HSV
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

        # Define range for typical heatmap colors (adjust based on actual chart)
        # Example: greenish/yellowish/reddish – you may need to calibrate
        lower = np.array([30, 50, 50])   # lower bound for green/yellow
        upper = np.array([90, 255, 255]) # upper bound
        mask = cv2.inRange(hsv, lower, upper)

        # Also include red tones (red wraps around in HSV, so two ranges)
        lower_red1 = np.array([0, 50, 50])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 50, 50])
        upper_red2 = np.array([180, 255, 255])
        mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask = cv2.bitwise_or(mask, mask_red1)
        mask = cv2.bitwise_or(mask, mask_red2)

        # Morphological operations to clean the mask
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise Exception("Could not locate heatmap region.")

        # Assume the largest contour is the heatmap
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)

        # Convert to screen coordinates
        self.chart_bbox = (self.window_region[0] + x, self.window_region[1] + y, w, h)
        return self.chart_bbox

class PriceAxisReader:
    def __init__(self, chart_bbox, tess_config="--psm 6 -c tessedit_char_whitelist=0123456789$,.KMB"):
        self.chart_bbox = chart_bbox
        self.tess_config = tess_config

    def detect_rows(self):
        # Take screenshot of the chart region
        with mss.mss() as sct:
            monitor = {"left": self.chart_bbox[0], "top": self.chart_bbox[1],
                       "width": self.chart_bbox[2], "height": self.chart_bbox[3]}
            img = np.array(sct.grab(monitor))
            gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

        # Detect horizontal lines using HoughLines or edge detection + morphology
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi/180, threshold=100, minLineLength=100, maxLineGap=10)

        if lines is None:
            return []

        # Filter horizontal lines (approx. 90°)
        h_lines = [line[0] for line in lines if abs(line[0][1] - line[0][3]) < 5]  # small y difference
        # Sort by y coordinate
        h_lines.sort(key=lambda x: x[1])

        # The lines define row boundaries; we can take midpoints between consecutive lines
        row_y_centers = []
        for i in range(len(h_lines)-1):
            y1 = h_lines[i][1]
            y2 = h_lines[i+1][1]
            if y2 - y1 > 20:  # minimum row height
                row_y_centers.append((y1 + y2) // 2)

        return row_y_centers

    def get_price_labels(self, row_centers):
        # For each row, crop the leftmost part of the chart (where price labels appear)
        # and run OCR
        prices = []
        left_margin_width = 100  # assume labels are within first 100px; may need adjustment
        with mss.mss() as sct:
            for y_center in row_centers:
                # Define region for the price label (x from chart left, y around row center)
                label_region = {
                    "left": self.chart_bbox[0],
                    "top": self.chart_bbox[1] + y_center - 15,
                    "width": left_margin_width,
                    "height": 30
                }
                img = np.array(sct.grab(label_region))
                gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                # Preprocess: threshold, scale up for better OCR
                _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
                scaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
                text = pytesseract.image_to_string(scaled, config=self.tess_config).strip()
                # Clean common OCR errors
                text = text.replace(' ', '').replace('$', '').replace(',', '')
                prices.append(text)
        return prices

class DataExtractor:
    def __init__(self, chart_bbox, row_y_centers, price_labels, tooltip_region_size=(200, 60)):
        self.chart_bbox = chart_bbox
        self.row_y_centers = row_y_centers
        self.price_labels = price_labels
        self.tooltip_w, self.tooltip_h = tooltip_region_size
        self.results = []

    def extract_all(self, log_callback=None):
        # Assume the heatmap has one column (vertical axis = price). If multiple columns exist,
        # you'd need to detect them similarly. For simplicity, we click at a fixed horizontal
        # position inside the heatmap (e.g., centre of the heatmap width).
        click_x = self.chart_bbox[0] + self.chart_bbox[2] // 2

        for idx, y_center in enumerate(self.row_y_centers):
            click_y = self.chart_bbox[1] + y_center

            # Click the cell
            pyautogui.click(click_x, click_y)
            time.sleep(0.5)  # Wait for tooltip to appear

            # Capture tooltip region (below the click point, adjust if needed)
            tooltip_left = click_x - self.tooltip_w // 2
            tooltip_top = click_y + 20  # assume tooltip appears below cursor
            tooltip_region = {
                "left": tooltip_left,
                "top": tooltip_top,
                "width": self.tooltip_w,
                "height": self.tooltip_h
            }

            with mss.mss() as sct:
                img = np.array(sct.grab(tooltip_region))
                gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                # Preprocess: threshold, invert if needed
                _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
                # OCR
                text = pytesseract.image_to_string(thresh, config="--psm 7 -c tessedit_char_whitelist=0123456789.KM")
                value = text.strip().replace(' ', '')

            price_val = self.price_labels[idx] if idx < len(self.price_labels) else "Unknown"
            self.results.append({
                "price": price_val,
                "liquidation": value
            })

            if log_callback:
                log_callback(f"[Deepseek] Extracted: Price={price_val}, Liquidation={value}")

            # Optional: small delay between clicks
            time.sleep(0.2)

        return self.results

class DataSaver:
    @staticmethod
    def save_to_file(data, filename="liquidation_data.txt"):
        with open(filename, 'w') as f:
            for item in data:
                f.write(f"{item['price']}\t{item['liquidation']}\n")

class DeepseekHeatmapExtractor:
    def __init__(self, config, log_callback):
        self.config = config
        self._log = log_callback

    def run(self, pair_name):
        self._log(f"[Deepseek] Starting extraction for {pair_name}")
        try:
            # Step 1: Focus Coinglass window
            focus = WindowFocus("Coinglass")
            focus.focus_window()
            window = focus.window
            window_region = (window.left, window.top, window.width, window.height)
            self._log(f"[Deepseek] Window focused: {window_region}")

            # Step 2: Locate the heatmap chart
            locator = ChartLocator(window_region)
            chart_bbox = locator.locate_chart()
            self._log(f"[Deepseek] Chart located at: {chart_bbox}")

            # Step 3: Detect row positions and price labels
            price_reader = PriceAxisReader(chart_bbox)
            row_centers = price_reader.detect_rows()
            if not row_centers:
                self._log("[Deepseek] [ERROR] No rows detected. Adjust line detection parameters.")
                return False

            price_labels = price_reader.get_price_labels(row_centers)
            self._log(f"[Deepseek] Detected {len(price_labels)} price levels: {price_labels}")

            # Step 4: Extract liquidation values
            extractor = DataExtractor(chart_bbox, row_centers, price_labels)
            results = extractor.extract_all(self._log)

            # Step 5: Save results
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(root_dir, "learned_data")
            os.makedirs(data_dir, exist_ok=True)
            filename = os.path.join(data_dir, f"deepseek_liquidation_data_{pair_name}.txt")

            DataSaver.save_to_file(results, filename)
            self._log(f"[Deepseek] Data saved to {filename}")

            return True

        except Exception as e:
            self._log(f"[Deepseek] [ERROR] {e}")
            import traceback
            self._log(f"[Deepseek] {traceback.format_exc()}")
            return False
