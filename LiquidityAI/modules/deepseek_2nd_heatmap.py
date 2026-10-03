import cv2
import numpy as np
import pytesseract
import pyautogui
import pygetwindow as gw
import mss
import time
import re
import os

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class OCRReader:
    def __init__(self, log_callback=None):
        self._log = log_callback or print
        # PSM 6 = Assume a single uniform block of text (good for price axis)
        self.tesseract_config = '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789.,'

    def read_text(self, image):
        """Extract text from an image (numpy array) using Tesseract."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Coinglass has light text on dark background → use THRESH_BINARY_INV
        # or use adaptive threshold for robustness
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Scale up for better OCR accuracy
        scaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
        text = pytesseract.image_to_string(scaled, config=self.tesseract_config)
        return text.strip()

    def read_numbers_with_boxes(self, image):
        """Return list of (text, (x,y,w,h)) for numbers in image."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Try multiple thresholding strategies for robustness
        results = []
        strategies = [
            ("otsu", lambda g: cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
            ("otsu_inv", lambda g: cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]),
            ("adaptive", lambda g: cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)),
            ("adaptive_inv", lambda g: cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)),
        ]

        for name, threshold_fn in strategies:
            try:
                thresh = threshold_fn(gray)
                scaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
                data = pytesseract.image_to_data(scaled, config=self.tesseract_config, output_type=pytesseract.Output.DICT)
                for i, text in enumerate(data['text']):
                    cleaned = text.strip().replace(',', '').replace(' ', '')
                    if cleaned and re.match(r'^[\d\.]+$', cleaned):
                        # Halve coordinates back (we scaled 2x)
                        x = data['left'][i] // 2
                        y = data['top'][i] // 2
                        w = data['width'][i] // 2
                        h = data['height'][i] // 2
                        results.append((cleaned, (x, y, w, h)))
                if results:
                    self._log(f"[OCR] Strategy '{name}' found {len(results)} numbers")
                    break
            except Exception as e:
                self._log(f"[OCR] Strategy '{name}' failed: {e}")
                continue

        return results

class ScreenCapture:
    def __init__(self):
        self.sct = mss.mss()

    def capture_region(self, region):
        """Capture a specific region (left, top, width, height)."""
        return np.array(self.sct.grab(region))

    def capture_window(self, window_title):
        """Capture the whole window by title."""
        windows = gw.getWindowsWithTitle(window_title)
        if not windows:
            raise Exception(f"Window '{window_title}' not found")
        win = windows[0]
        # In PyQt environment, aggressive activate might fail or need retry, handled by AutomatorHelper
        region = {'left': win.left, 'top': win.top, 'width': win.width, 'height': win.height}
        return self.capture_region(region), (win.left, win.top)

class CoinglassAutomatorHelper:
    def bring_to_front(self, window_title):
        """Bring Coinglass window to front using pygetwindow."""
        windows = gw.getWindowsWithTitle(window_title)
        if windows:
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.5)
            return True
        return False

    def click(self, x, y):
        pyautogui.click(x, y)
        time.sleep(0.3)

    def press_esc(self):
        pyautogui.press('esc')
        time.sleep(0.2)

class Deepseek2ndHeatmapExtractor:
    def __init__(self, config, log_callback):
        self.config = config
        self._log = log_callback
        self.ocr = OCRReader(log_callback=log_callback)
        self.capturer = ScreenCapture()
        self.automator = CoinglassAutomatorHelper()

    def run(self, pair_name):
        self._log(f"[Deepseek-2nd] Starting extraction for {pair_name}")
        window_title = "Coinglass"
        try:
            self._log("[Deepseek-2nd] Bringing Coinglass to front...")
            if not self.automator.bring_to_front(window_title):
                self._log("[Deepseek-2nd] Coinglass window not found. Please open it manually.")
                return False

            # Optional: recenter the chart around the current price so the
            # heatmap and price axis are in a consistent position before we
            # start scanning / clicking. We intentionally do NOT perform any
            # extra zooming here so we don't squash the boxes off‑screen; the
            # zoom level should come from your saved Coinglass layout.
            try:
                from modules.coinglass_automator import CoinglassAutomator

                self._log("[Deepseek-2nd] Centering chart on current price before extraction...")
                ca = CoinglassAutomator(config=self.config, log_callback=self._log)
                # Use slightly wider default bands so the important liquidity
                # area is visible; caller can override via config if needed.
                upper_blocks = int(self.config.get("ds2_upper_blocks", 8))
                lower_blocks = int(self.config.get("ds2_lower_blocks", 8))
                ca.center_chart_on_price(upper_blocks=upper_blocks, lower_blocks=lower_blocks)
            except Exception as e:
                self._log(f"[Deepseek-2nd] [WARN] Could not center chart automatically: {e}")

            self._log("[Deepseek-2nd] Capturing window...")
            window_img_bgra, (offset_x, offset_y) = self.capturer.capture_window(window_title)
            window_img = cv2.cvtColor(window_img_bgra, cv2.COLOR_BGRA2BGR)

            self._log("[Deepseek-2nd] Locating price axis and heatmap...")
            price_axis_rect, heatmap_rect = self._find_price_axis_and_heatmap(window_img)

            # Extract price levels from the axis region
            # Ensure the crop coordinates are safe and within the image shape
            h, w = window_img.shape[:2]
            p_l = max(0, price_axis_rect[0])
            p_t = max(0, price_axis_rect[1])
            p_r = min(w, price_axis_rect[0] + price_axis_rect[2])
            p_b = min(h, price_axis_rect[1] + price_axis_rect[3])
            
            price_axis_img = window_img[p_t:p_b, p_l:p_r]
            
            if price_axis_img.size == 0:
                self._log("[Deepseek-2nd] Price axis image bounds were empty. Aborting.")
                return False
            
            # Save debug images so user can verify what we're reading
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            debug_dir = os.path.join(root_dir, "debug_ds2")
            os.makedirs(debug_dir, exist_ok=True)
            cv2.imwrite(os.path.join(debug_dir, "price_axis_crop.png"), price_axis_img)
            cv2.imwrite(os.path.join(debug_dir, "full_window.png"), window_img)
            self._log(f"[Deepseek-2nd] Debug images saved to {debug_dir}")
            self._log(f"[Deepseek-2nd] Price axis crop shape: {price_axis_img.shape}")
            self._log(f"[Deepseek-2nd] Price axis bounds: l={p_l} t={p_t} r={p_r} b={p_b}")
                
            price_levels = self._extract_price_levels(price_axis_img, offset_y + p_t)
            if not price_levels:
                # We can still continue using prices read directly from the popup
                # grid; the axis-based mapping will just be unavailable.
                self._log("[Deepseek-2nd] WARNING: No price labels detected on axis; "
                          "will rely on popup table prices only.")
            elif len(price_levels) < 2:
                # In some zoom/layouts Coinglass only renders a single price label
                # on the right axis. In that case we still continue so that at
                # least the liquidity values are captured, but we log a warning
                # because interpolation will be very rough.
                self._log(f"[Deepseek-2nd] WARNING: Only {len(price_levels)} price level detected on axis. "
                          "Axis-based price mapping may be less accurate.")

            # Detect clickable positions: first try the vertical column of red
            # dots near the right side (strong signal of high-liquidity boxes),
            # then fall back to generic colored-cell detection on the heatmap.
            h_l = max(0, heatmap_rect[0])
            h_t = max(0, heatmap_rect[1])
            h_r = min(w, heatmap_rect[0] + heatmap_rect[2])
            h_b = min(h, heatmap_rect[1] + heatmap_rect[3])
            
            heatmap_img = window_img[h_t:h_b, h_l:h_r]
            if heatmap_img.size == 0:
                self._log("[Deepseek-2nd] Heatmap image bounds were empty. Aborting.")
                return False

            # 1) Try dedicated red-dot detector operating on the narrow strip
            #    between heatmap and price axis (where the dots live).
            cells = self._detect_red_dots(window_img, offset_x, offset_y, price_axis_rect, heatmap_rect)
            self._log(f"[Deepseek-2nd] Red-dot detector found {len(cells)} cells.")

            # 2) Fallback: generic colored-cell clustering inside heatmap area.
            if not cells:
                cells = self._detect_heatmap_cells(heatmap_img, offset_x + h_l, offset_y + h_t)
                self._log(f"[Deepseek-2nd] Fallback heatmap-cell detector found {len(cells)} cells.")

            # Map cells to prices and read popups. Final price comes from the
            # popup grid itself (right column), and we only fall back to the
            # axis-based approximate mapping if OCR fails to find a price.
            results = []
            for (cell_x, cell_y) in cells:
                approx_price = self._map_y_to_price(cell_y, price_levels) if price_levels else None
                if approx_price is not None:
                    self._log(f"[Deepseek-2nd] Clicking cell near price ~{approx_price:.4f}...")
                else:
                    self._log(f"[Deepseek-2nd] Clicking cell at y={cell_y} (no axis mapping)...")

                popup_data = self._click_and_read_popup(cell_x, cell_y)
                if popup_data is not None:
                    popup_price_str, value_str = popup_data

                    # Prefer the exact price string read from the table; if OCR
                    # missed it, fall back to approximate axis-mapped price.
                    if popup_price_str:
                        try:
                            price_num = float(popup_price_str.replace(',', ''))
                        except ValueError:
                            price_num = approx_price
                    else:
                        price_num = approx_price

                    if price_num is None or not value_str:
                        continue

                    results.append((price_num, value_str))
                    self._log(f"[Deepseek-2nd]   -> price={price_num:.5f}, liq={value_str}")
                else:
                    self._log("[Deepseek-2nd]   -> No popup detected")

            # Save results
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            out_dir = os.path.join(root_dir, "output")
            os.makedirs(out_dir, exist_ok=True)
            output_file = os.path.join(out_dir, f"{pair_name}_liquidation_data_ds2.txt")
            
            with open(output_file, 'w') as f:
                for price, value in sorted(results, key=lambda r: r[0]):
                    f.write(f"{price:.5f}: {value}\n")
            self._log(f"[Deepseek-2nd] Data saved to {output_file}")

            # Also mirror this data into the learned_data folder so that the
            # Predictions tab ("Liquidity Data (From heatmaps)") can display it.
            learned_dir = os.path.join(root_dir, "learned_data")
            os.makedirs(learned_dir, exist_ok=True)
            ui_file = os.path.join(learned_dir, f"liquidity_data_{pair_name}.txt")

            try:
                with open(ui_file, 'w', encoding='utf-8') as f_ui:
                    f_ui.write(f"=== Deepseek 2nd Heatmap Data for {pair_name} ===\n")
                    f_ui.write(f"Captured at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    if results:
                        for price, value in sorted(results, key=lambda r: r[0]):
                            f_ui.write(f"{price:.5f}: {value}\n")
                    else:
                        f_ui.write("No liquidity cells detected.\n")
                self._log(f"[Deepseek-2nd] UI liquidity file updated at {ui_file}")
            except Exception as e:
                self._log(f"[Deepseek-2nd] [WARN] Failed to write UI liquidity file: {e}")
            return True
            
        except Exception as e:
            self._log(f"[Deepseek-2nd] [ERROR] {e}")
            import traceback
            self._log(f"[Deepseek-2nd] {traceback.format_exc()}")
            return False

    def _find_price_axis_and_heatmap(self, img):
        """Heuristic: price axis is on the right; heatmap is on the left."""
        h, w = img.shape[:2]
        axis_width = 120 # Fixed width is usually better for right-side axis 
        
        # Heatmap is from left edge to start of axis
        heatmap_rect = (0, 0, w - axis_width, h)
        # Price axis is the rightmost part
        price_axis_rect = (w - axis_width, 0, axis_width, h)
        
        return price_axis_rect, heatmap_rect

    def _extract_price_levels(self, axis_img, axis_top_y):
        """Read numbers from price axis and return list of (price, screen_y)."""
        numbers = self.ocr.read_numbers_with_boxes(axis_img)
        levels = []
        for text, (x, y, w, h) in numbers:
            try:
                # Convert text like "1.3840" to float
                price = float(text.strip().replace(',', ''))
                # y is within axis_img; convert to screen y
                screen_y = axis_top_y + y + h//2   # center of text
                levels.append((price, screen_y))
            except ValueError:
                continue
        # Sort by y (top to bottom)
        levels.sort(key=lambda x: x[1])
        # Optional: validate step consistency
        return levels

    def _detect_red_dots(self, window_img, offset_x, offset_y, price_axis_rect, heatmap_rect):
        """
        Detect the vertical column of small red dots rendered in front of
        high‑liquidity boxes. These usually sit between the heatmap body and
        the right price axis.
        """
        h, w = window_img.shape[:2]

        # Define a vertical strip that hugs the left edge of the price axis and
        # slightly overlaps into the heatmap body. This is where the dots live.
        axis_x = price_axis_rect[0]
        strip_left = max(0, axis_x - 70)
        strip_right = min(w, axis_x + 10)
        strip_width = max(1, strip_right - strip_left)

        strip = window_img[:, strip_left:strip_right]
        hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)

        # Red hue ranges (wrap around HSV wheel)
        red_low1 = np.array([0, 120, 120])
        red_high1 = np.array([10, 255, 255])
        red_low2 = np.array([160, 120, 120])
        red_high2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, red_low1, red_high1)
        mask2 = cv2.inRange(hsv, red_low2, red_high2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        kernel = np.ones((3, 3), np.uint8)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cells = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 5 or area > 400:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            local_cx = int(M["m10"] / M["m00"])
            local_cy = int(M["m01"] / M["m00"])
            cx = strip_left + local_cx + offset_x
            cy = local_cy + offset_y
            cells.append((cx, cy))

        cells.sort(key=lambda p: p[1])
        return cells

    def _detect_heatmap_cells(self, heatmap_img, heatmap_left, heatmap_top):
        """
        Detect clickable positions for liquidity tooltips.

        Coinglass renders a vertical column of small red dots on the right side
        of the heatmap – each dot corresponds to a high-intensity liquidity box.
        We prioritise those dots (better signal, fewer useless clicks). If no
        red dots are found we fall back to a generic colored-cell detector.
        """
        hsv = cv2.cvtColor(heatmap_img, cv2.COLOR_BGR2HSV)
        h, w = hsv.shape[:2]

        # ── 1) Try to detect the vertical strip of red dots on right side ──
        # Work only on the rightmost ~18% of the heatmap where the dots live.
        band_x0 = int(w * 0.82)
        band = hsv[:, band_x0:]

        # Red in HSV is split near 0 and 180.
        red_low1 = np.array([0, 120, 120])
        red_high1 = np.array([10, 255, 255])
        red_low2 = np.array([160, 120, 120])
        red_high2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(band, red_low1, red_high1)
        mask2 = cv2.inRange(band, red_low2, red_high2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        kernel = np.ones((3, 3), np.uint8)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dot_cells = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Dots are small but not single-pixel; tune bounds generously.
            if area < 5 or area > 300:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            local_cx = int(M["m10"] / M["m00"])
            local_cy = int(M["m01"] / M["m00"])
            cx = band_x0 + local_cx + heatmap_left
            cy = local_cy + heatmap_top
            dot_cells.append((cx, cy))

        if dot_cells:
            # Sort by vertical position so we click from top to bottom.
            dot_cells.sort(key=lambda p: p[1])
            self._log(f"[Deepseek-2nd] Using {len(dot_cells)} red-dot liquidity markers.")
            return dot_cells

        # ── 2) Fallback: generic colored-cell clustering across whole heatmap ──
        lower = np.array([0, 50, 50])
        upper = np.array([180, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cells = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 50:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"]) + heatmap_left
            cy = int(M["m01"] / M["m00"]) + heatmap_top
            cells.append((cx, cy))

        # Still sort vertically to produce a tidy scan.
        cells.sort(key=lambda p: p[1])
        return cells

    def _map_y_to_price(self, screen_y, price_levels):
        """Find price for a given screen y via linear interpolation."""
        if not price_levels:
            return None
        # price_levels is list of (price, y) sorted by y
        ys = [y for _, y in price_levels]
        prices = [p for p, _ in price_levels]
        if screen_y <= ys[0]:
            return prices[0]
        if screen_y >= ys[-1]:
            return prices[-1]
        # find interval
        for i in range(len(ys)-1):
            if ys[i] <= screen_y <= ys[i+1]:
                # linear interpolation
                ratio = (screen_y - ys[i]) / (ys[i+1] - ys[i])
                return prices[i] + ratio * (prices[i+1] - prices[i])
        return None

    def _click_and_read_popup(self, x, y):
        """
        Click at (x,y), wait for popup, OCR its content, dismiss.

        Returns:
            (price_str, liquidity_str) on success, or None if nothing readable.
            price_str  – e.g. "1.3700" from the right-hand column of the grid.
            liquidity_str – e.g. "2.2M" (largest volume found in the grid).
        """
        # Define region where popup might appear (e.g., near top‑right of chart)
        # We'll search a larger area around the click.
        search_region = (max(0, x-200), max(0, y-200), 400, 400)   # left, top, width, height
        # Capture before
        before_bgra = self.capturer.capture_region({
            'left': search_region[0], 'top': search_region[1],
            'width': search_region[2], 'height': search_region[3]
        })
        before = cv2.cvtColor(before_bgra, cv2.COLOR_BGRA2BGR)

        # Click
        self.automator.click(x, y)
        time.sleep(0.8)   # wait for popup
        # Capture after
        after_bgra = self.capturer.capture_region({
            'left': search_region[0], 'top': search_region[1],
            'width': search_region[2], 'height': search_region[3]
        })
        after = cv2.cvtColor(after_bgra, cv2.COLOR_BGRA2BGR)

        # Find changes: absolute difference
        diff = cv2.absdiff(cv2.cvtColor(before, cv2.COLOR_BGR2GRAY),
                           cv2.cvtColor(after, cv2.COLOR_BGR2GRAY))
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_crop = None
        best_area = 0
        for cnt in contours:
            if cv2.contourArea(cnt) < 100:
                continue
            x_c, y_c, w_c, h_c = cv2.boundingRect(cnt)
            # Expect popup grid to be reasonably wide and tall, but not full-screen.
            if 80 < w_c < 450 and 40 < h_c < 260:
                area = w_c * h_c
                if area > best_area:
                    best_area = area
                    best_crop = after[y_c:y_c+h_c, x_c:x_c+w_c]

        price_str = None
        liq_str = None

        if best_crop is not None:
            # Preprocess for OCR: grayscale + upscale + adaptive threshold
            gray = cv2.cvtColor(best_crop, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
            thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 11, 2)

            # Use a more permissive config to capture both prices and K/M values
            text = pytesseract.image_to_string(thr, config='--oem 3 --psm 6')
            self._log(f"[Deepseek-2nd] Popup OCR (truncated): {text[:120].replace(chr(10), ' ')}")

            lines = [ln.strip() for ln in text.split('\n') if ln.strip()]

            # Prices: plain decimals like 1.3700
            price_re = re.compile(r'\b\d{1,6}\.\d{1,5}\b')
            # Liquidity: numbers with K/M/B suffix
            vol_re = re.compile(r'\b\d+(?:\.\d+)?\s*[KMBkmb]\b')

            all_prices = []
            all_vols = []
            for ln in lines:
                all_prices.extend(price_re.findall(ln))
                all_vols.extend(vol_re.findall(ln))

            if all_prices:
                # Right-hand column in the grid usually lists prices vertically;
                # the last price in reading order tends to be the clicked level.
                price_str = all_prices[-1]

            if all_vols:
                # Choose the largest liquidity (e.g., 2.2M instead of smaller sub-cells).
                def vol_to_val(vs):
                    s = vs.upper().replace(' ', '')
                    if 'B' in s:
                        return float(s.replace('B', '')) * 1_000_000_000
                    if 'M' in s:
                        return float(s.replace('M', '')) * 1_000_000
                    if 'K' in s:
                        return float(s.replace('K', '')) * 1_000
                    try:
                        return float(s)
                    except ValueError:
                        return 0.0

                liq_str = max(all_vols, key=vol_to_val)

        # Dismiss popup
        self.automator.press_esc()
        if price_str or liq_str:
            return price_str, liq_str
        return None
