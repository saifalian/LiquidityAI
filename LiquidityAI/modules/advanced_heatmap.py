import os
import cv2
import mss
import time
import csv
import re
import numpy as np
import pyautogui
import pytesseract

class AdvancedHeatmapExtractor:
    def __init__(self, config=None, log_callback=None):
        self.config = config or {}
        self.log_callback = log_callback
        self.sct = mss.mss()
        self.scan_rows = 80
        self.scan_cols = 40
        self.click_delay = 0.15
        self.tooltip_delay = 0.25

    def _log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
        else:
            print(msg)

    def grab(self, region):
        """High-Speed Screen Capture"""
        img = self.sct.grab(region)
        return np.array(img)[:, :, :3]  # Drop alpha channel

    def preprocess_for_ocr(self, img):
        """Image Preprocessing for OCR"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        thresh = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11,
            2
        )
        return thresh

    def read_tooltip(self, img):
        """Tooltip OCR Reader"""
        processed = self.preprocess_for_ocr(img)
        config = "--psm 6"
        # Assuming tesseract is in path, or configured in main setup
        text = pytesseract.image_to_string(processed, config=config)
        return text

    def parse_liquidity(self, text):
        """Liquidity Parser"""
        match = re.search(r'([\d\.]+)\s*(K|M|B)', text, re.IGNORECASE)
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2).upper()
        multiplier = {
            "K": 1e3,
            "M": 1e6,
            "B": 1e9
        }
        return value * multiplier.get(unit, 1)

    def read_price_axis(self, img):
        """Price Axis Reader (converts pixel -> price limit)"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        text = pytesseract.image_to_string(gray)
        prices = []
        for line in text.split("\n"):
            try:
                # Basic cleaning
                clean_line = line.replace(",", "").strip()
                prices.append(float(clean_line))
            except:
                pass
        return prices

    def build_price_mapper(self, top_price, bottom_price, height):
        """Pixel -> Price Mapping"""
        price_per_pixel = (top_price - bottom_price) / height
        def pixel_to_price(y):
            return top_price - (y * price_per_pixel)
        return pixel_to_price

    def detect_liquidity_clusters(self, img):
        """Heatmap Liquidity Detection"""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # Assuming heatmap colors for liquidity clusters
        lower = np.array([0, 120, 120])
        upper = np.array([10, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        points = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            cx = x + w // 2
            cy = y + h // 2
            points.append((cx, cy))
        return points

    def scan_points(self, points, chart_offset):
        """Grid Scanner for specific points"""
        data = []
        for x, y in points:
            sx = chart_offset["left"] + x
            sy = chart_offset["top"] + y
            pyautogui.moveTo(sx, sy)
            pyautogui.click()
            time.sleep(self.tooltip_delay)
            
            # Grab tooltip box around cursor for OCR
            region = {
                "left": max(0, sx - 150),
                "top": max(0, sy - 150),
                "width": 300,
                "height": 300
            }
            tooltip_img = self.grab(region)
            text = self.read_tooltip(tooltip_img)
            liquidity = self.parse_liquidity(text)
            
            data.append((sy, liquidity))
        return data

    def save_data(self, rows, path):
        """Data Writer"""
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["pixel_y", "liquidity"])
            for r in rows:
                writer.writerow(r)

    def focus_chart_window(self, title):
        """Window Manager"""
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(title)
        if not windows:
            return None
        window = windows[0]
        if window.isMinimized:
            import win32gui
            import win32con
            win32gui.ShowWindow(window._hWnd, win32con.SW_RESTORE)
        window.activate()
        return {
            "left": window.left,
            "top": window.top,
            "width": window.width,
            "height": window.height
        }

    def run(self, pair_name):
        self._log(f"[AdvancedHeatmap] Starting heatmap extraction for {pair_name}...")
        
        # 1. Focus chart window
        chart = self.focus_chart_window("Coinglass")
        if not chart:
            self._log("[AdvancedHeatmap] Coinglass window not found! Ensure it's open.")
            return False
            
        time.sleep(1.0) # wait for window to come forward

        # 2. Grab chart image
        self._log("[AdvancedHeatmap] Grabbing chart screenshot...")
        img = self.grab(chart)

        # 3. Detect heatmap clusters
        self._log("[AdvancedHeatmap] Detecting liquidity clusters in chart...")
        points = self.detect_liquidity_clusters(img)
        self._log(f"[AdvancedHeatmap] Found {len(points)} clusters to scan.")

        if not points:
            self._log("[AdvancedHeatmap] No clusters found! Are colors matched correctly?")
            return True # Not necessarily an error, just empty

        # 4. Scan clusters
        self._log("[AdvancedHeatmap] Scanning points for tooltips...")
        scanned = self.scan_points(points, chart)

        # 5. Save data
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out_dir = os.path.join(root_dir, "learned_data")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"liquidity_data_{pair_name}.csv")
        
        self.save_data(scanned, out_path)
        self._log(f"[AdvancedHeatmap] Finished scanning. Saved to {out_path}.")
        return True
