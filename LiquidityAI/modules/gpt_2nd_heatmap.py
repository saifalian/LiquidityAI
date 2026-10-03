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
import csv

# Set Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class Gpt2ndHeatmapExtractor:
    def __init__(self, config, log_callback):
        self.config = config
        self._log = log_callback

    def focus_window(self, window_title_substring="Coinglass"):
        windows = gw.getWindowsWithTitle(window_title_substring)
        if not windows:
            raise Exception(f"No window with title containing '{window_title_substring}' found.")
        window = windows[0]
        if window.isMinimized:
            win32gui.ShowWindow(window._hWnd, win32con.SW_RESTORE)
        window.activate()
        time.sleep(1)
        return window

    def _screenshot_cv(self, monitor=None):
        with mss.mss() as sct:
            if monitor is None:
                monitor = sct.monitors[0]
            img = np.array(sct.grab(monitor))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def run(self, pair_name):
        self._log(f"[GPT-2nd] Starting extraction for {pair_name}")
        try:
            # 1. Focus
            window = self.focus_window()
            win_region = {"left": window.left, "top": window.top, "width": window.width, "height": window.height}
            
            # 2. Screenshot
            img = self._screenshot_cv(win_region)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # 3. Detect Chart Area
            # Using typical dark purple / heatmap background ranges
            lower_bg = np.array([120, 50, 50])
            upper_bg = np.array([170, 255, 255])
            mask_bg = cv2.inRange(hsv, lower_bg, upper_bg)
            
            contours_bg, _ = cv2.findContours(mask_bg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours_bg:
                self._log("[GPT-2nd] Heatmap region not found. Using naive bounds.")
                x, y, w, h = 0, 0, img.shape[1], img.shape[0]
            else:
                largest = max(contours_bg, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest)
                
            heatmap_box = (x + window.left, y + window.top, w, h)
            self._log(f"[GPT-2nd] Heatmap Box detected at: {heatmap_box}")

            # 4. Detect Price Axis
            price_axis = img[y:y+h, -120:] # crop right 120 pixels of the detected y-h range
            gray = cv2.cvtColor(price_axis, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            scaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
            
            text = pytesseract.image_to_string(scaled, config="--psm 6 -c tessedit_char_whitelist=0123456789.,").strip()
            
            prices = []
            for line in text.split("\n"):
                line_clean = line.replace(",", "")
                try:
                    prices.append(float(line_clean))
                except ValueError:
                    continue
                    
            if len(prices) >= 2:
                top_price = max(prices)
                bottom_price = min(prices)
                price_per_pixel = (top_price - bottom_price) / h
                self._log(f"[GPT-2nd] Price range: {bottom_price} - {top_price}, pp_pixel: {price_per_pixel:.6f}")
            else:
                self._log("[GPT-2nd] Could not parse min/max prices from axis.")
                top_price, price_per_pixel = 0, 0

            # 5. Detect Liquidity Blocks (Dark purple/Red intense regions)
            lower_blocks = np.array([0, 120, 120])
            upper_blocks = np.array([20, 255, 255]) 
            roi_hsv = hsv[y:y+h, x:x+w]
            mask_blocks = cv2.inRange(roi_hsv, lower_blocks, upper_blocks)
            block_contours, _ = cv2.findContours(mask_blocks, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            points_to_click = []
            for c in block_contours:
                if cv2.contourArea(c) > 10: 
                    bx, by, bw, bh = cv2.boundingRect(c)
                    cx = x + bx + bw//2
                    cy = y + by + bh//2
                    points_to_click.append((cx, cy))
            
            # Sort by X to go left to right, or Y to go top to bottom
            points_to_click.sort(key=lambda p: p[1])
            # Limit points to avoid excessive clicking
            points_to_click = points_to_click[:30]
            self._log(f"[GPT-2nd] Detected {len(points_to_click)} high-intensity liquidity blocks to scan.")
            
            # 6. Click block and capture tooltip table
            results = []
            for (cx, cy) in points_to_click:
                pyautogui.click(window.left + cx, window.top + cy)
                time.sleep(0.4) 
                
                table_region = {
                    "left": window.left + window.width - 400,
                    "top": window.top + 150,
                    "width": 380,
                    "height": 400
                }
                
                with mss.mss() as sct:
                    table_img = np.array(sct.grab(table_region))
                    t_gray = cv2.cvtColor(table_img, cv2.COLOR_BGRA2GRAY)
                    _, t_thresh = cv2.threshold(t_gray, 200, 255, cv2.THRESH_BINARY)
                    t_text = pytesseract.image_to_string(t_thresh, config="--psm 6 -c tessedit_char_whitelist=0123456789.KM")
                    val = t_text.strip()
                    
                    lines = [l for l in val.split('\n') if l.strip()]
                    liq_val = lines[0] if lines else "0"

                if price_per_pixel > 0:
                    pixel_y = cy - y
                    price = top_price - (pixel_y * price_per_pixel)
                else:
                    price = 0.0
                    
                results.append([f"{price:.4f}", liq_val])
                self._log(f"[GPT-2nd] Block at Y={cy} -> Price: {price:.4f}, Liquidity: {liq_val}")

            # 7. Save Data
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            out_dir = os.path.join(root_dir, "output")
            os.makedirs(out_dir, exist_ok=True)
            filename = os.path.join(out_dir, f"liquidity_data_{pair_name}.csv")
            
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["price", "liquidity"])
                for r in results:
                    writer.writerow(r)
                    
            self._log(f"[GPT-2nd] Data saved to {filename}")
            return True

        except Exception as e:
            self._log(f"[GPT-2nd] [ERROR] {e}")
            import traceback
            self._log(f"[GPT-2nd] {traceback.format_exc()}")
            return False
