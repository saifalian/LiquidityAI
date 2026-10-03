import pyautogui
import pygetwindow as gw
import time
import subprocess
import os
import ctypes
import ctypes.wintypes
import numpy as np

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Try to import win32 for taskbar icon clicking
try:
    import win32gui
    import win32con
    import win32api
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class CoinglassAutomator:
    def __init__(self, config=None, log_callback=None):
        self.config = config or {}
        self.log_callback = log_callback  # callable(str) to emit log messages to UI
        self._cancelled = False
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

    def cancel(self):
        """Signal the automator to stop immediately."""
        self._cancelled = True

    def _log(self, msg):
        """Send message to UI log area."""
        print(msg)
        if self.log_callback:
            self.log_callback(msg)

    # ─────────────────────────────────────────────────────────────
    # 1.  Find / Open Coinglass
    # ─────────────────────────────────────────────────────────────

    def find_coinglass_window(self):
        """Return the Coinglass window object, or None if not found."""
        # Try exact known titles first, then partial match
        for title in ['Coinglass', 'coinglass']:
            windows = gw.getWindowsWithTitle(title)
            if windows:
                return windows[0]
        # Partial-match fallback across all open windows
        try:
            all_windows = gw.getAllWindows()
            for w in all_windows:
                if 'coinglass' in w.title.lower() and w.width > 0:
                    return w
        except Exception:
            pass
        return None

    def bring_coinglass_to_front(self):
        """
        Try to find and activate the Coinglass window.
        Returns True if successful.
        """
        win = self.find_coinglass_window()
        if win:
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(1.2)
                self._log("[Automator] Coinglass window found and activated.")
                # Wait for any loading spinner to finish before returning
                self.wait_for_loading()
                return True
            except Exception as e:
                self._log(f"[Automator] Window found but could not activate: {e}")
        return False

    # ─────────────────────────────────────────────────────────────
    # Loading spinner detection (color-based, works for any rotation)
    # ─────────────────────────────────────────────────────────────

    # Golden amber HSV range of the Coinglass spinner
    # H: 30-55°  S: 60-100%  V: 60-100%   (golden/amber tone)
    _SPINNER_HSV_LOW  = np.array([15, 120, 120], dtype=np.uint8)   # OpenCV H=0-180
    _SPINNER_HSV_HIGH = np.array([35, 255, 255], dtype=np.uint8)
    _SPINNER_MIN_PX   = 40   # minimum matching pixels to count as "spinner visible"

    def is_loading(self):
        """
        Returns True if the golden Coinglass loading spinner is currently
        visible anywhere on screen.
        Uses HSV color range detection – works regardless of rotation angle.
        """
        if not HAS_PIL:
            return False
        try:
            import cv2
            # Grab a screenshot, restrict to the Coinglass window if possible
            win = self.find_coinglass_window()
            if win:
                region = (win.left, win.top, win.width, win.height)
                img = pyautogui.screenshot(region=region)
            else:
                img = pyautogui.screenshot()

            # Convert PIL -> numpy BGR -> HSV
            frame = np.array(img)
            bgr   = frame[:, :, ::-1]          # RGB -> BGR
            hsv   = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

            mask  = cv2.inRange(hsv, self._SPINNER_HSV_LOW, self._SPINNER_HSV_HIGH)
            count = cv2.countNonZero(mask)
            return count >= self._SPINNER_MIN_PX

        except Exception:
            return False

    def wait_for_loading(self, timeout=30, poll=0.4):
        """
        Block until the golden Coinglass loading spinner disappears,
        or until `timeout` seconds have elapsed.

        Detection uses HSV color matching so it works at any rotation angle
        and requires NO reference image file.
        Falls back to a 2-second wait if opencv-python is not installed.
        """
        try:
            import cv2  # noqa — just checking availability
        except ImportError:
            self._log("[Automator] opencv not found – waiting 2s for load.")
            time.sleep(2)
            return

        deadline     = time.time() + timeout
        spinner_seen = False

        while time.time() < deadline:
            if self._cancelled:
                return

            if self.is_loading():
                if not spinner_seen:
                    self._log("[Automator] Loading spinner detected – waiting...")
                spinner_seen = True
                time.sleep(poll)
            else:
                if spinner_seen:
                    self._log("[Automator] Loading complete ✓")
                time.sleep(0.3)   # tiny buffer after spinner disappears
                return

        self._log("[Automator] [WARN] Loading wait timed out – proceeding anyway.")

    def find_coinglass_in_taskbar(self):
        """
        Search the Windows taskbar for the Coinglass icon using its title/class.
        Returns True if found and clicked successfully.
        """
        if not HAS_WIN32:
            self._log("[Automator] win32gui not available – cannot search taskbar.")
            return False

        self._log("[Automator] Searching taskbar for Coinglass icon...")

        # Enumerate all top-level windows that are on the taskbar
        found_hwnd = []

        def enum_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if 'coinglass' in title.lower():
                    found_hwnd.append(hwnd)
            return True

        win32gui.EnumWindows(enum_callback, None)

        if found_hwnd:
            hwnd = found_hwnd[0]
            self._log(f"[Automator] Found Coinglass HWND={hwnd} in taskbar. Restoring...")
            try:
                # SW_RESTORE = 9
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(1.5)
                return True
            except Exception as e:
                self._log(f"[Automator] Could not restore Coinglass: {e}")

        return False

    def click_taskbar_icon_by_image(self):
        """
        Fallback: look for the Coinglass icon image ONLY in the taskbar strip
        at the bottom of the screen. After clicking, verifies that the
        Coinglass window actually appeared to prevent clicking wrong apps.
        Requires 'coinglass_icon.png' to be placed next to this file.
        """
        icon_path = os.path.join(os.path.dirname(__file__), 'coinglass_icon.png')
        if not os.path.exists(icon_path):
            self._log("[Automator] coinglass_icon.png not found – skipping image search.")
            return False

        try:
            import pyautogui as _pag
            screen_w, screen_h = _pag.size()

            # Only look inside the taskbar strip (bottom ~48 px of screen)
            taskbar_region = (0, screen_h - 80, screen_w, 80)
            self._log("[Automator] Searching taskbar strip for Coinglass icon...")

            loc = _pag.locateOnScreen(
                icon_path,
                region=taskbar_region,
                confidence=0.75,
                grayscale=True
            )
            if loc:
                cx, cy = _pag.center(loc)
                self._log(f"[Automator] Taskbar icon found at ({cx}, {cy}). Clicking...")
                _pag.click(cx, cy)
                time.sleep(2.5)

                # ── VERIFY Coinglass actually appeared ──
                if self.find_coinglass_window():
                    self._log("[Automator] Verified: Coinglass window is now open.")
                    return True
                else:
                    self._log("[Automator] WARNING: Click did not open Coinglass – wrong icon clicked?")
                    return False
            else:
                self._log("[Automator] Coinglass icon not found in taskbar strip.")
        except Exception as e:
            self._log(f"[Automator] Image search error: {e}")
        return False

    def launch_coinglass_exe(self):
        """
        Try to launch the Coinglass desktop application.
        Looks for the exe path in config first, then common install locations.
        Returns True if a launch was attempted (does not guarantee success).
        """
        # Prefer a user-configured path
        exe = self.config.get('coinglass_exe', '')
        if not exe:
            # Common default install paths
            candidates = [
                r"C:\Program Files\Coinglass\Coinglass.exe",
                r"C:\Program Files (x86)\Coinglass\Coinglass.exe",
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Coinglass', 'Coinglass.exe'),
                os.path.join(os.environ.get('APPDATA', ''), 'Coinglass', 'Coinglass.exe'),
            ]
            for c in candidates:
                if os.path.isfile(c):
                    exe = c
                    break

        if exe and os.path.isfile(exe):
            self._log(f"[Automator] Launching Coinglass from: {exe}")
            try:
                subprocess.Popen([exe])
                time.sleep(5)  # give it time to start
                return True
            except Exception as e:
                self._log(f"[Automator] Failed to launch exe: {e}")
        else:
            self._log("[Automator] Coinglass exe not found. Set 'coinglass_exe' in config.json.")
        return False

    def ensure_coinglass_open(self, max_attempts=3, retry_delay=3):
        """
        Keep trying to find / open Coinglass.  Order of priority:
          1. Activate existing window by title (most reliable, title-based)
          2. win32gui enumerate all windows for any with 'coinglass' in title
          3. Image-based search RESTRICTED to taskbar strip + verify window appeared
          4. Launch the Coinglass.exe directly
          5. Repeat up to max_attempts, then give up.
        Returns True when the window is reachable, False if all attempts fail.
        """
        for attempt in range(1, max_attempts + 1):
            if self._cancelled:
                self._log("[Automator] Cancelled by user.")
                return False

            self._log(f"[Automator] Attempt {attempt}/{max_attempts}: Looking for Coinglass...")

            # Step 1: direct window title search (safest)
            if self.bring_coinglass_to_front():
                return True

            if self._cancelled:
                return False

            # Step 2: win32 taskbar enumeration (title-based, no image matching)
            if self.find_coinglass_in_taskbar():
                time.sleep(1)
                if self.bring_coinglass_to_front():
                    return True

            if self._cancelled:
                return False

            # Step 3: image-based ONLY in the taskbar strip + verification
            if self.click_taskbar_icon_by_image():
                time.sleep(1)
                if self.bring_coinglass_to_front():
                    return True

            if self._cancelled:
                return False

            # Step 4: try launching the exe (only on first attempt to avoid spam)
            if attempt == 1:
                if self.launch_coinglass_exe():
                    # After launch, give it time then retry the window search
                    if self.bring_coinglass_to_front():
                        return True

            self._log(f"[Automator] Coinglass not found. Retrying in {retry_delay}s...")
            for _ in range(int(retry_delay / 0.5)):
                if self._cancelled:
                    self._log("[Automator] Cancelled by user.")
                    return False
                time.sleep(0.5)

        self._log("[Automator] [FAIL] Could not find or open Coinglass after all attempts.")
        return False

    # ─────────────────────────────────────────────────────────────
    # 2.  Navigate to a pair inside Coinglass
    # ─────────────────────────────────────────────────────────────

    def search_and_select_pair(self, pair_name, exchange="Binance"):
        """
        Exact Coinglass UI flow:
          1. Ensure Coinglass is open.
          2. Click the small [v] chevron dropdown next to the current pair.
          3. In the popup that opens, click the 'Search coin' input field.
          4. Type the pair name (e.g. XRPUSDT).
          5. Click the FIRST result that appears in the list below.
          6. Wait for the chart to reload.
        Returns True on success, False on failure.
        """
        if not self.ensure_coinglass_open():
            return False

        self._log(f"[Automator] Selecting pair '{pair_name}'...")

        try:
            # ── Step 1: click the [v] dropdown arrow ────────────────────────
            self._log("[Automator] Step 1: Clicking dropdown arrow...")
            dropdown_pos = self._click_pair_dropdown()
            if dropdown_pos is None:
                return False
            time.sleep(1.0)          # wait for popup to open
            self.wait_for_loading()

            # ── Step 2: click the 'Search coin' field inside the popup ───────
            self._log("[Automator] Step 2: Clicking 'Search coin' field...")
            search_pos = self._click_search_coin_field(dropdown_pos)
            if search_pos is None:
                self._log("[Automator] [FAIL] Could not find Search coin field.")
                pyautogui.press('escape')
                return False
            time.sleep(0.5)

            # ── Step 3: type the coin name ───────────────────────────────────
            self._log(f"[Automator] Step 3: Typing '{pair_name}'...")
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.typewrite(pair_name, interval=0.07)
            time.sleep(1.8)          # wait for results to appear

            # ── Step 4: click the first result ──────────────────────────────
            self._log("[Automator] Step 4: Clicking first result...")
            clicked = self._click_first_result(search_pos)
            if not clicked:
                self._log("[Automator] [WARN] Could not find result row – pressing Enter.")
                pyautogui.press('enter')

            time.sleep(1.0)
            self.wait_for_loading()   # chart reloads after selection
            self._log(f"[Automator] [OK] '{pair_name}' selected successfully.")

            # ── Step 5: apply per-pair slider range from reference image ──────
            slider_img   = self.config.get('slider_img', '')
            set_min      = self.config.get('set_slider_min', True)
            set_max      = self.config.get('set_slider_max', True)
            if slider_img and os.path.exists(slider_img) and (set_min or set_max):
                self._log(f"[Automator] Step 5: Applying slider range from image...")
                self.set_slider_range_from_image(slider_img, set_min=set_min, set_max=set_max)
            elif slider_img and not os.path.exists(slider_img):
                self._log(f"[Automator] [WARN] Slider image not found: {slider_img}")

            return True

        except pyautogui.FailSafeException:
            self._log("[Automator] Aborted by FailSafe (mouse moved to corner).")
            return False
        except Exception as e:
            self._log(f"[Automator] Error during pair search: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # Sub-steps for the pair-selection flow
    # ─────────────────────────────────────────────────────────────

    def _click_pair_dropdown(self):
        """
        Click the small [v] chevron next to the current pair label.

        Priority order:
          1. 'pair_dropdown_bbox' in config.json   (most accurate)
          2. Image match with modules/coinglass_dropdown.png
          3. Window-relative fallback (center-right area, ~100px from top)

        Returns (cx, cy) of the click on success, None on failure.
        """
        win = self.find_coinglass_window()
        if not win:
            self._log("[Automator] [FAIL] Coinglass window not found.")
            return None

        # Option 1: calibrated position from config
        bbox = self.config.get('pair_dropdown_bbox')
        if bbox:
            cx = bbox['left'] + bbox['width'] // 2
            cy = bbox['top']  + bbox['height'] // 2
            self._log(f"[Automator] Dropdown: using calibrated ({cx},{cy})")
            pyautogui.moveTo(cx, cy, duration=0.3)
            pyautogui.click()
            return (cx, cy)

        # Option 2: image match
        img = os.path.join(os.path.dirname(__file__), 'coinglass_dropdown.png')
        if os.path.exists(img):
            try:
                loc = pyautogui.locateOnScreen(img, confidence=0.75)
                if loc:
                    cx, cy = pyautogui.center(loc)
                    self._log(f"[Automator] Dropdown: image match at ({cx},{cy})")
                    pyautogui.moveTo(cx, cy, duration=0.3)
                    pyautogui.click()
                    return (cx, cy)
            except Exception as e:
                self._log(f"[Automator] Dropdown image search error: {e}")

        # Option 3: window-relative fallback
        # Layout observed from Coinglass screenshot:
        #   Row 1 (nav tabs: Liquidations, Funding etc.)  ≈ top + 45px
        #   Row 2 (SPOT | Binance XXXX | [v] | 5m)        ≈ top + 85px
        # The [v] chevron sits at roughly 73% of window width in row 2.
        cx = win.left + int(win.width * 0.73)
        cy = win.top  + 85
        self._log(f"[Automator] Dropdown: fallback position ({cx},{cy})")
        self._log("[Automator] TIP: For accurate clicks, save a screenshot of the")
        self._log("[Automator]      [v] button as modules/coinglass_dropdown.png")
        self._log("[Automator]      OR add 'pair_dropdown_bbox' to config.json")
        pyautogui.moveTo(cx, cy, duration=0.3)
        pyautogui.click()
        return (cx, cy)

    def _click_search_coin_field(self, dropdown_pos):
        """
        Find and click the 'Search Coin' input field that appears after
        clicking the dropdown arrow.

        Priority order:
          1. 'search_coin_bbox' in config.json
          2. Image match with modules/coinglass_search_field.png   ← primary
          3. Positional fallback relative to dropdown button

        Returns (cx, cy) of the click, None on failure.
        """
        # Option 1: calibrated coords from config
        bbox = self.config.get('search_coin_bbox')
        if bbox:
            cx = bbox['left'] + bbox['width'] // 2
            cy = bbox['top']  + bbox['height'] // 2
            self._log(f"[Automator] Search field: using calibrated ({cx},{cy})")
            pyautogui.moveTo(cx, cy, duration=0.3)
            pyautogui.click()
            return (cx, cy)

        # Option 2: image match (most reliable)
        img = os.path.join(os.path.dirname(__file__), 'coinglass_search_field.png')
        if os.path.exists(img):
            try:
                loc = pyautogui.locateOnScreen(img, confidence=0.75, grayscale=True)
                if loc:
                    cx, cy = pyautogui.center(loc)
                    self._log(f"[Automator] Search field: image match at ({cx},{cy})")
                    pyautogui.moveTo(cx, cy, duration=0.3)
                    pyautogui.click()
                    time.sleep(0.2)
                    # Clear any pre-filled text
                    pyautogui.hotkey('ctrl', 'a')
                    return (cx, cy)
            except Exception as e:
                self._log(f"[Automator] Search field image error: {e}")

        # Option 3: positional fallback
        # The Search Coin bar appears roughly below+left of the dropdown chevron
        if dropdown_pos:
            cx = dropdown_pos[0] - 150
            cy = dropdown_pos[1] + 50
            self._log(f"[Automator] Search field: fallback position ({cx},{cy})")
            self._log("[Automator] TIP: Save the search bar as modules/coinglass_search_field.png")
            pyautogui.moveTo(cx, cy, duration=0.3)
            pyautogui.click()
            return (cx, cy)

        return None


    def _click_first_result(self, search_pos):
        """
        After typing in the search field, click the FIRST result in the list.

        Priority order:
          1. Image match with modules/coinglass_first_result.png
          2. Fallback: click ~55px below the search field
             (the first result row appears just below the search input)

        Returns True if clicked, False otherwise.
        """
        # Option 1: image match for the first result row
        img = os.path.join(os.path.dirname(__file__), 'coinglass_first_result.png')
        if os.path.exists(img):
            try:
                loc = pyautogui.locateOnScreen(img, confidence=0.70)
                if loc:
                    cx, cy = pyautogui.center(loc)
                    self._log(f"[Automator] First result: image match at ({cx},{cy})")
                    pyautogui.moveTo(cx, cy, duration=0.3)
                    pyautogui.click()
                    return True
            except Exception as e:
                self._log(f"[Automator] First result image error: {e}")

        # Option 2: click directly below the search field
        if search_pos:
            cx = search_pos[0]
            cy = search_pos[1] + 55    # first result row ~55px below search field
            self._log(f"[Automator] First result: fallback click at ({cx},{cy})")
            pyautogui.moveTo(cx, cy, duration=0.3)
            pyautogui.click()
            return True

        return False

    # ─────────────────────────────────────────────────────────────
    # 3.  Slider control
    # ─────────────────────────────────────────────────────────────

    def adjust_slider(self, action):
        """Drags the threshold slider left or right (legacy single-handle adjust)."""
        slider_bbox = self.config.get('slider_bbox')
        if not slider_bbox:
            self._log("[Automator] 'slider_bbox' not found in config.")
            return
        center_x = slider_bbox['left'] + slider_bbox['width'] // 2
        center_y = slider_bbox['top']  + slider_bbox['height'] // 2
        drag_distance = 15
        try:
            pyautogui.moveTo(center_x, center_y, duration=0.2)
            if action == 'increase_threshold':
                pyautogui.drag(drag_distance, 0, duration=0.2, button='left')
            elif action == 'decrease_threshold':
                pyautogui.drag(-drag_distance, 0, duration=0.2, button='left')
        except pyautogui.FailSafeException:
            self._log("[Automator] Slider adjustment aborted by FailSafe.")

    # ─────────────────────────────────────────────────────────────
    # Image-based slider range setter
    # ─────────────────────────────────────────────────────────────

    def _detect_handles_from_image(self, img_path):
        """
        Analyze a reference screenshot of the Coinglass color-range slider.
        Returns (min_ratio, max_ratio) where each is a 0.0–1.0 proportion
        of the slider width, representing where the left and right handles are.

        Detection:
          - Converts the image to HSV
          - Finds columns that contain 'colored' pixels (saturation > 40)
          - Leftmost colored column  → left handle (min)
          - Rightmost colored column → right handle (max)
        """
        if not HAS_PIL:
            self._log("[Automator] PIL not available – cannot analyze slider image.")
            return (0.0, 1.0)
        try:
            import cv2
            img = cv2.imread(img_path)
            if img is None:
                self._log(f"[Automator] Could not read image: {img_path}")
                return (0.0, 1.0)

            h, w = img.shape[:2]
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            # Saturation channel: low = gray/white, high = colored
            sat = hsv[:, :, 1]
            colored_mask = sat > 40           # colored pixels

            # Find columns that have at least one colored pixel
            colored_cols = np.where(np.any(colored_mask, axis=0))[0]
            if len(colored_cols) == 0:
                self._log("[Automator] [WARN] No colored pixels found in slider image – using defaults.")
                return (0.0, 1.0)

            min_x = int(colored_cols[0])
            max_x = int(colored_cols[-1])

            min_ratio = min_x / w
            max_ratio = max_x / w
            self._log(f"[Automator] Slider image analysis: "
                      f"left handle at {min_ratio:.3f} ({min_x}px), "
                      f"right handle at {max_ratio:.3f} ({max_x}px)")
            return (min_ratio, max_ratio)

        except ImportError:
            self._log("[Automator] opencv not installed – cannot analyze slider image.")
            return (0.0, 1.0)
        except Exception as e:
            self._log(f"[Automator] Slider image analysis error: {e}")
            return (0.0, 1.0)

    def set_slider_range_from_image(self, img_path, set_min=True, set_max=True):
        """
        1. Analyze the reference image to find where left/right handles are.
        2. Map those proportions to the actual slider X positions on screen.
        3. Click at the LEFT  handle screen position (if set_min=True).
        4. Click at the RIGHT handle screen position (if set_max=True).

        If per-handle captured coordinates (min_click_x/y, max_click_x/y)
        are available in config, use those directly instead of calculating.

        Y coordinate priority (for calculated mode):
          1. 'slider_click_y' in config.json  ← exact absolute screen Y (most reliable)
          2. slider_bbox top + height//2       ← fallback from bounding box
        """
        # ── Check for directly captured per-handle coordinates ──
        min_cx = self.config.get('min_click_x')
        min_cy = self.config.get('min_click_y')
        max_cx = self.config.get('max_click_x')
        max_cy = self.config.get('max_click_y')

        has_direct_min = min_cx is not None and min_cy is not None
        has_direct_max = max_cx is not None and max_cy is not None

        if has_direct_min or has_direct_max:
            self._log("[Automator] Using directly captured click coordinates.")
            try:
                if set_min and has_direct_min:
                    self._log(f"[Automator] Clicking MIN at ({min_cx}, {min_cy})")
                    pyautogui.moveTo(int(min_cx), int(min_cy), duration=0.4)
                    pyautogui.click()
                    time.sleep(0.4)

                if set_max and has_direct_max:
                    self._log(f"[Automator] Clicking MAX at ({max_cx}, {max_cy})")
                    pyautogui.moveTo(int(max_cx), int(max_cy), duration=0.4)
                    pyautogui.click()
                    time.sleep(0.4)

                self._log("[Automator] Slider range applied ✓")
            except pyautogui.FailSafeException:
                self._log("[Automator] Slider click aborted by FailSafe.")
            except Exception as e:
                self._log(f"[Automator] Slider click error: {e}")
            return

        # ── Fallback: calculate from slider_bbox + image detection ──
        slider_bbox = self.config.get('slider_bbox')
        if not slider_bbox:
            self._log("[Automator] [WARN] slider_bbox not in config.json – cannot set slider.")
            self._log("[Automator]        Add slider_bbox and slider_click_y to config.json.")
            return

        min_ratio, max_ratio = self._detect_handles_from_image(img_path)

        left  = slider_bbox['left']
        width = slider_bbox['width']

        # ── Determine the Y coordinate to click ────────────────────────────
        slider_click_y = self.config.get('slider_click_y')
        slider_y_offset = int(self.config.get('slider_y_offset', 0))

        if slider_click_y is not None:
            cy = int(slider_click_y)
            self._log(f"[Automator] Using calibrated slider_click_y={cy}")
        else:
            cy = slider_bbox['top'] + slider_bbox['height'] // 2
            self._log(f"[Automator] slider_click_y not set – using bbox fallback y={cy}")
            self._log("[Automator] TIP: If the click lands too high, add")
            self._log("[Automator]      \"slider_y_offset\": <positive_pixels> to config.json")
            self._log("[Automator]      OR set \"slider_click_y\": <exact_y> for exact positioning")

        if slider_y_offset != 0:
            self._log(f"[Automator] Applying slider_y_offset={slider_y_offset:+d} → y={cy} → {cy + slider_y_offset}")
            cy += slider_y_offset

        min_x = left + int(min_ratio * width)
        max_x = left + int(max_ratio * width)

        self._log(f"[Automator] Slider will click: MIN=({min_x}, {cy})  MAX=({max_x}, {cy})")

        try:
            if set_min:
                self._log(f"[Automator] Clicking LEFT handle at ({min_x}, {cy})")
                pyautogui.moveTo(min_x, cy, duration=0.4)
                pyautogui.click()
                time.sleep(0.4)

            if set_max:
                self._log(f"[Automator] Clicking RIGHT handle at ({max_x}, {cy})")
                pyautogui.moveTo(max_x, cy, duration=0.4)
                pyautogui.click()
                time.sleep(0.4)

            self._log("[Automator] Slider range applied ✓")

        except pyautogui.FailSafeException:
            self._log("[Automator] Slider click aborted by FailSafe.")
        except Exception as e:
            self._log(f"[Automator] Slider click error: {e}")

    # ─────────────────────────────────────────────────────────────
    # 4. Center Chart on Current Price  (premade macro step)
    # ─────────────────────────────────────────────────────────────

    def center_chart_on_price(self, upper_blocks=5, lower_blocks=5):
        """
        Detect the current-price indicator (the bright green/teal label on
        the right axis of the Coinglass chart) and drag/pan the chart so
        that the price is positioned vertically at a ratio determined by
        upper_blocks and lower_blocks.

        If upper_blocks=10 and lower_blocks=5, the price will be placed
        at 1/3 from the bottom (giving 2/3 space above for the 10 upper blocks).

        Saves debug images (debug_axis_roi.png, debug_mask.png) next to
        this file so the user can verify detection visually.

        Returns True on success, False on failure.
        """
        try:
            import cv2
        except ImportError:
            self._log("[Automator] opencv-python is required for center_chart. "
                       "pip install opencv-python")
            return False

        # 1. Find the Coinglass window ──────────────────────────────────────
        win = self.find_coinglass_window()
        if not win:
            self._log("[Automator] Cannot center chart – Coinglass window not found.")
            return False

        win_left   = win.left
        win_top    = win.top
        win_width  = win.width
        win_height = win.height
        self._log(f"[Automator] Coinglass window: ({win_left},{win_top}) {win_width}x{win_height}")

        # Estimate the chart drawing area (exclude toolbars / nav)
        #   Top: ~85px = title bar + Perpetual/SPOT tabs + slider bar
        #   Bottom: ~60px = timestamp row + bottom nav (Home, Markets …)
        #   Right: ~70px = price axis labels
        chart_top    = win_top  + 85
        chart_bottom = win_top  + win_height - 60
        chart_left   = win_left + 10
        chart_right  = win_left + win_width - 70

        chart_cx = (chart_left + chart_right)  // 2
        chart_cy = (chart_top  + chart_bottom) // 2

        # 2. Take a screenshot and find the price label ─────────────────────
        screenshot = pyautogui.screenshot()
        img_rgb = np.array(screenshot)
        img_bgr = img_rgb[:, :, ::-1]   # RGB → BGR for OpenCV

        # Crop to the right-axis strip (wider region to be safe)
        axis_l = max(0, win_left + win_width - 120)
        axis_r = min(img_bgr.shape[1], win_left + win_width)
        axis_t = max(0, win_top + 30)
        axis_b = min(img_bgr.shape[0], win_top + win_height - 30)

        roi = img_bgr[axis_t:axis_b, axis_l:axis_r]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Save debug images so user can verify what we see
        debug_dir = os.path.dirname(__file__)
        try:
            cv2.imwrite(os.path.join(debug_dir, 'debug_axis_roi.png'), roi)
        except Exception:
            pass

        # Try multiple HSV ranges — the price label can be GREEN or RED
        # depending on whether price is going up or down
        hsv_ranges = [
            # Green / teal shades
            (np.array([35, 60, 60], dtype=np.uint8),  np.array([90, 255, 255], dtype=np.uint8),  "green/teal"),
            (np.array([80, 60, 60], dtype=np.uint8),  np.array([100, 255, 255], dtype=np.uint8), "cyan"),
            (np.array([25, 40, 40], dtype=np.uint8),  np.array([105, 255, 255], dtype=np.uint8), "wide green"),
            # Red shades (wraps around H=0 in HSV)
            (np.array([0, 60, 60], dtype=np.uint8),   np.array([10, 255, 255], dtype=np.uint8),  "red-low"),
            (np.array([160, 60, 60], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8), "red-high"),
        ]

        best_contour = None
        best_area = 0
        best_range_name = ""

        for low, high, name in hsv_ranges:
            mask = cv2.inRange(hsv, low, high)
            px_count = cv2.countNonZero(mask)
            self._log(f"[Automator] HSV range '{name}': {px_count} matching pixels")

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                            cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(largest)
                if area > best_area:
                    best_area = area
                    best_contour = largest
                    best_range_name = name
                    # Save the winning mask for debug
                    try:
                        cv2.imwrite(os.path.join(debug_dir, 'debug_mask.png'), mask)
                    except Exception:
                        pass

        if best_contour is None or best_area < 30:
            self._log(f"[Automator] Could not detect the price label. Best area={best_area}px")
            self._log(f"[Automator] Debug images saved to {debug_dir}")
            self._log("[Automator] Check debug_axis_roi.png to verify the right axis is captured correctly.")
            return False

        bx, by, bw, bh = cv2.boundingRect(best_contour)
        self._log(f"[Automator] Best match: range='{best_range_name}', "
                  f"bbox=({bx},{by},{bw},{bh}), area={best_area}px")

        # Price label center in absolute screen coords
        price_screen_y = axis_t + by + bh // 2

        self._log(f"[Automator] Price label at screen Y={price_screen_y}, "
                  f"chart center Y={chart_cy}")

        # 3. Vertical centering ─────────────────────────────────────────────
        #    Position the price at a ratio based on upper/lower blocks.
        #    If upper=10, lower=5, total=15 → price should be at
        #    lower/(total) = 5/15 = 33% from the bottom, i.e. 67% from top.
        total_blocks = upper_blocks + lower_blocks
        if total_blocks > 0:
            # Ratio from top: upper_blocks take the space above
            ratio_from_top = upper_blocks / total_blocks
        else:
            ratio_from_top = 0.5
        target_y = chart_top + int((chart_bottom - chart_top) * ratio_from_top)
        self._log(f"[Automator] Center target: {upper_blocks} upper / {lower_blocks} lower → price at {ratio_from_top:.0%} from top, target Y={target_y}")

        #    Drag on the RIGHT PRICE AXIS (not chart area) — most trading
        #    charts only allow vertical pan on the Y-axis strip.
        dy = price_screen_y - target_y
        price_axis_x = win_left + win_width - 40   # middle of the price axis strip
        if abs(dy) > 10:
            self._log(f"[Automator] Vertical offset = {dy}px, dragging on price axis …")
            pyautogui.moveTo(price_axis_x, price_screen_y, duration=0.15)
            time.sleep(0.05)
            pyautogui.drag(0, -dy, duration=0.5, button='left')
            time.sleep(0.5)
        else:
            self._log("[Automator] Price already near target position.")

        # 4. Horizontal centering ───────────────────────────────────────────
        #    The most-recent candle is typically near the right edge.
        #    Use a conservative estimate (~70 %) and halve the drag amount
        #    to avoid overshooting.
        latest_x = chart_left + int((chart_right - chart_left) * 0.70)
        dx = latest_x - chart_cx
        if abs(dx) > 20:
            drag_amount = dx // 2   # halve to avoid overshoot
            self._log(f"[Automator] Horizontal offset ≈ {dx}px, dragging by {-drag_amount}px …")
            pyautogui.moveTo(chart_cx, chart_cy, duration=0.15)
            time.sleep(0.05)
            pyautogui.drag(-drag_amount, 0, duration=0.5, button='left')
            time.sleep(0.3)
        else:
            self._log("[Automator] Latest candle already near horizontal center.")

        self._log("[Automator] ✅ Chart centered on current price.")
        return True

    # ─────────────────────────────────────────────────────────────
    # 5. Custom Macro Execution
    # ─────────────────────────────────────────────────────────────

    def execute_macro(self, pair_name, steps):
        """
        Executes a custom sequence of visually recorded steps instead of the hardcoded flow.
        Supports IF blocks (jumps forward to corresponding end_if if condition fails).
        """
        self._log(f"[Automator] Starting custom macro for '{pair_name}' ({len(steps)} steps)...")
        
        def _find_end_if(start_idx):
            depth = 1
            for j in range(start_idx + 1, len(steps)):
                t = steps[j].get('type')
                if t in ('if_detected', 'if_not_detected'):
                    depth += 1
                elif t == 'end_if':
                    depth -= 1
                    if depth == 0:
                        return j
            return len(steps) # fallback to end
            
        def _check_image(img_path, timeout, want_visible=True, log_prefix=""):
            if not img_path or not os.path.exists(img_path):
                self._log(f"[Automator] [FAIL] Image not found on disk: {img_path}")
                return False, None
                
            self._log(f"[Automator] {log_prefix} Wait up to {timeout}s for {os.path.basename(img_path)}")
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self._cancelled: return False, None
                found_center = None
                try:
                    loc = pyautogui.locateCenterOnScreen(img_path, confidence=0.8)
                    if loc: found_center = loc
                except pyautogui.ImageNotFoundException:
                    pass
                except Exception:
                    try:
                        loc = pyautogui.locateCenterOnScreen(img_path)
                        if loc: found_center = loc
                    except pyautogui.ImageNotFoundException:
                        pass
                        
                if want_visible and found_center:
                    return True, found_center
                elif not want_visible and not found_center:
                    return True, None
                    
                time.sleep(0.5)
                
            return False, None
            
        i = 0
        while i < len(steps):
            if self._cancelled:
                self._log("[Automator] Macro execution cancelled.")
                return False
                
            step = steps[i]
            t = step.get('type')
            delay = step.get('delay', 0)
            self._log(f"[Automator] [Step {i+1}] Executing {t}...")
            
            try:
                jump_to_end_if = False
                
                if t == 'click':
                    pyautogui.moveTo(step['x'], step['y'], duration=0.2)
                    pyautogui.click()
                elif t == 'swipe':
                    pyautogui.moveTo(step['start_x'], step['start_y'], duration=0.2)
                    pyautogui.dragTo(step['end_x'], step['end_y'], duration=0.5, button='left')
                elif t == 'type':
                    text = step.get('text', '').replace('{pair}', pair_name)
                    pyautogui.typewrite(text, interval=0.07)
                elif t == 'key':
                    pyautogui.press(step.get('key', 'enter'))
                elif t == 'find_coinglass':
                    if not self.ensure_coinglass_open():
                        self._log("[Automator] [FAIL] Could not find Coinglass. Aborting macro.")
                        return False
                elif t == 'center_chart':
                    c_upper = step.get('upper_blocks', 5)
                    c_lower = step.get('lower_blocks', 5)
                    if not self.center_chart_on_price(upper_blocks=c_upper, lower_blocks=c_lower):
                        self._log("[Automator] [WARN] Center chart failed – continuing anyway.")
                elif t == 'learn_liquidity':
                    upper = step.get('upper_blocks', 5)
                    lower = step.get('lower_blocks', 5)
                    if not self.learn_liquidity_data(pair_name, upper_blocks=upper, lower_blocks=lower):
                        self._log("[Automator] [WARN] Learn Liquidity Data failed – continuing anyway.")
                elif t == 'advanced_center_chart':
                    if not self.advanced_center_chart(pair_name):
                        self._log("[Automator] [WARN] Advanced Center Chart failed – continuing anyway.")
                elif t == 'chatgpt_model':
                    self._log("[Automator] Executing 'chatpt model for reading 111'...")
                    from modules.advanced_heatmap import AdvancedHeatmapExtractor
                    extractor = AdvancedHeatmapExtractor(self.config, self._log)
                    success = extractor.run(pair_name)
                    if not success:
                        self._log("[Automator] [WARN] chatpt model step failed.")

                elif t == 'deepseek_reader':
                    self._log("[Automator] Executing 'deepseek reader 11'...")
                    from modules.deepseek_heatmap import DeepseekHeatmapExtractor
                    extractor = DeepseekHeatmapExtractor(self.config, self._log)
                    success = extractor.run(pair_name)
                    if not success:
                        self._log("[Automator] [WARN] deepseek reader 11 step failed.")

                elif t == 'gpt_2nd':
                    self._log("[Automator] Executing 'gpt 2nd'...")
                    from modules.gpt_2nd_heatmap import Gpt2ndHeatmapExtractor
                    extractor = Gpt2ndHeatmapExtractor(self.config, self._log)
                    success = extractor.run(pair_name)
                    if not success:
                        self._log("[Automator] [WARN] gpt 2nd step failed.")

                elif t == 'deepseek_2nd':
                    self._log("[Automator] Executing 'deepseek 2nd'...")
                    from modules.deepseek_2nd_heatmap import Deepseek2ndHeatmapExtractor
                    extractor = Deepseek2ndHeatmapExtractor(self.config, self._log)
                    success = extractor.run(pair_name)
                    if not success:
                        self._log("[Automator] [WARN] deepseek 2nd step failed.")

                elif t in ('wait_image', 'click_image'):
                    found, center = _check_image(step.get('image_path'), step.get('timeout', 30.0), want_visible=True)
                    if not found:
                        self._log(f"[Automator] [FAIL] Timed out finding image.")
                        return False
                    if t == 'click_image' and center:
                        self._log(f"[Automator] Found image at {center}")
                        pyautogui.moveTo(center.x, center.y, duration=0.2)
                        pyautogui.click()
                elif t == 'wait_disappear':
                    found, _ = _check_image(step.get('image_path'), step.get('timeout', 30.0), want_visible=False, log_prefix="[DISAPPEAR]")
                    if not found:
                        self._log(f"[Automator] [FAIL] Timed out waiting for image to disappear.")
                        return False
                    self._log(f"[Automator] Image successfully disappeared.")
                elif t == 'if_detected':
                    found, _ = _check_image(step.get('image_path'), step.get('timeout', 5.0), want_visible=True, log_prefix="[IF DETECT]")
                    if not found:
                        self._log(f"[Automator] [IF FAIL] Image not detected. Skipping block.")
                        jump_to_end_if = True
                    else:
                        self._log(f"[Automator] [IF PASS] Image detected. Entering block.")
                elif t == 'if_not_detected':
                    found, _ = _check_image(step.get('image_path'), step.get('timeout', 5.0), want_visible=False, log_prefix="[IF NOT DETECT]")
                    if not found:
                        self._log(f"[Automator] [IF FAIL] Image STILL detected. Skipping block.")
                        jump_to_end_if = True
                    else:
                        self._log(f"[Automator] [IF PASS] Image not detected. Entering block.")
                elif t == 'end_if':
                    pass # Ignore, block markers
                elif t == 'wait':
                    pass # Handled by standard delay sleep below
                    
                if jump_to_end_if:
                    i = _find_end_if(i)
                else:
                    if delay > 0 and not jump_to_end_if and t not in ('end_if', 'if_detected', 'if_not_detected'):
                        time.sleep(delay)
                        
            except pyautogui.FailSafeException:
                self._log("[Automator] Macro aborted by FailSafe (mouse in corner).")
                return False
            except Exception as e:
                self._log(f"[Automator] Error during macro step {i+1}: {e}")
                return False
                
            i += 1
                
        self._log(f"[Automator] Custom macro for '{pair_name}' completed successfully.")
        return True

    # ─────────────────────────────────────────────────────────────
    # 6. Advanced Center Chart
    # ─────────────────────────────────────────────────────────────

    def advanced_center_chart(self, pair_name):
        """
        1. Take screenshot, detect heatmap grid to estimate box height.
        2. Move chart horizontally so the latest candle is at chart center.
        3. Detect the dashed current-price line; drag vertically to center it.
        4. Scroll to fully zoom out.
        5. Analyse heatmap color intensity to find the highest-liquidity zone
           above AND below the current price line.
        6. Zoom back in so the view starts 3 boxes above the highest-liquidity
           zone (for the upper side).
        7. Save results to learned_data/advanced_center_{pair_name}.txt
        """
        try:
            import cv2
        except ImportError:
            self._log("[Automator] opencv-python required for Advanced Center Chart.")
            return False

        win = self.find_coinglass_window()
        if not win:
            self._log("[Automator] Advanced Center Chart: Coinglass window not found.")
            return False

        win_left   = win.left
        win_top    = win.top
        win_width  = win.width
        win_height = win.height

        # Chart margins (exclude top nav + bottom bar + right price axis)
        chart_top    = win_top  + 85
        chart_bottom = win_top  + win_height - 60
        chart_left   = win_left + 10
        chart_right  = win_left + win_width  - 70
        chart_cx     = (chart_left + chart_right)  // 2
        chart_cy     = (chart_top  + chart_bottom) // 2
        chart_h      = chart_bottom - chart_top

        self._log("[Automator] [AdvCenter] Step 1: Taking screenshot for heatmap analysis...")

        def _screenshot_cv():
            """Return a BGR OpenCV image of the full screen."""
            ss = pyautogui.screenshot()
            return cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2BGR)

        def _chart_roi(cv_img):
            """Crop to the chart area only."""
            return cv_img[chart_top:chart_bottom, chart_left:chart_right]

        # ── Step 1: Estimate grid box height ────────────────────────────────
        img = _screenshot_cv()
        roi = _chart_roi(img)
        roi_h = chart_bottom - chart_top

        # Detect horizontal grid lines by looking for thin light/white rows
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Sobel horizontal edges
        sobel = cv2.Sobel(gray_roi, cv2.CV_64F, 0, 1, ksize=3)
        sobel_abs = np.abs(sobel).astype(np.uint8)
        _, edge_mask = cv2.threshold(sobel_abs, 20, 255, cv2.THRESH_BINARY)
        row_sums = edge_mask.sum(axis=1)
        # Row gaps between high-edge rows give us box height
        strong_rows = np.where(row_sums > roi.shape[1] * 0.3)[0]
        if len(strong_rows) > 2:
            gaps = np.diff(strong_rows)
            typical_gaps = gaps[(gaps > 5) & (gaps < 200)]
            box_h = int(np.median(typical_gaps)) if len(typical_gaps) > 0 else 30
        else:
            box_h = 30  # fallback
        self._log(f"[Automator] [AdvCenter] Estimated grid box height: {box_h}px")

        # ── Step 2: Horizontal center ────────────────────────────────────────
        self._log("[Automator] [AdvCenter] Step 2: Horizontal centering...")
        latest_x = chart_left + int((chart_right - chart_left) * 0.75)
        dx = latest_x - chart_cx
        if abs(dx) > 20:
            drag_amount = dx // 2
            pyautogui.moveTo(chart_cx, chart_cy, duration=0.15)
            time.sleep(0.05)
            pyautogui.drag(-drag_amount, 0, duration=0.5, button='left')
            time.sleep(0.4)
            self._log(f"[Automator] [AdvCenter] Dragged horizontally by {-drag_amount}px.")
        else:
            self._log("[Automator] [AdvCenter] Already horizontally centered.")

        # ── Step 3: Detect dashed price line and center vertically ───────────
        self._log("[Automator] [AdvCenter] Step 3: Detecting current-price dashed line...")
        img = _screenshot_cv()
        roi = _chart_roi(img)

        # The price line is a thin dashed HORIZONTAL line
        # Strategy: look at the right-side price axis for the green/red label first
        axis_l = max(0, win_left + win_width - 120)
        axis_r = min(img.shape[1], win_left + win_width)
        axis_t = max(0, win_top + 30)
        axis_b = min(img.shape[0], win_top + win_height - 30)
        axis_roi = img[axis_t:axis_b, axis_l:axis_r]
        hsv_axis = cv2.cvtColor(axis_roi, cv2.COLOR_BGR2HSV)

        # Find the price label (green or red box on the axis)
        price_y_in_screen = None
        hsv_ranges = [
            (np.array([0, 60, 60],   dtype=np.uint8), np.array([10, 255, 255],  dtype=np.uint8)),
            (np.array([160, 60, 60], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8)),
            (np.array([35, 60, 60],  dtype=np.uint8), np.array([90, 255, 255],  dtype=np.uint8)),
        ]
        best_area = 0
        for lo, hi in hsv_ranges:
            mask = cv2.inRange(hsv_axis, lo, hi)
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cnts:
                c = max(cnts, key=cv2.contourArea)
                a = cv2.contourArea(c)
                if a > best_area:
                    best_area = a
                    _, by, _, bh = cv2.boundingRect(c)
                    price_y_in_screen = axis_t + by + bh // 2

        if price_y_in_screen is None:
            self._log("[Automator] [AdvCenter] Could not find price label – skipping vertical center.")
        else:
            self._log(f"[Automator] [AdvCenter] Price Y on screen: {price_y_in_screen}, target: {chart_cy}")
            dy = price_y_in_screen - chart_cy
            price_axis_x = win_left + win_width - 40
            if abs(dy) > 10:
                pyautogui.moveTo(price_axis_x, price_y_in_screen, duration=0.15)
                time.sleep(0.05)
                pyautogui.drag(0, -dy, duration=0.5, button='left')
                time.sleep(0.5)
                self._log(f"[Automator] [AdvCenter] Dragged vertically by {-dy}px. Chart is now centered.")
            else:
                self._log("[Automator] [AdvCenter] Already vertically centered.")

        # ── Step 4: Full zoom out ────────────────────────────────────────────
        self._log("[Automator] [AdvCenter] Step 4: Zooming out fully on the price axis (20 scroll steps)...")
        price_axis_x = win_left + win_width - 40
        pyautogui.moveTo(price_axis_x, chart_cy, duration=0.1)
        time.sleep(0.1)
        # Scroll DOWN over price axis = zoom out (compresses axis)
        # Assuming positive is scroll down/out based on user feedback
        for _ in range(20):
            pyautogui.scroll(120)  
            time.sleep(0.05)
        time.sleep(1.0)  # wait for chart to settle

        # ── Step 5: Detect highest liquidity intensity ───────────────────────
        self._log("[Automator] [AdvCenter] Step 5: Analysing heatmap color intensity...")
        
        def _get_intensity_zones():
            """Returns (best_above_y, best_above_intensity, best_below_y, best_below_intensity) in ROI coords"""
            img_curr = _screenshot_cv()
            roi_curr = _chart_roi(img_curr)
            hsv_roi_curr = cv2.cvtColor(roi_curr, cv2.COLOR_BGR2HSV)
            
            mask1 = cv2.inRange(hsv_roi_curr, np.array([0, 80, 40], dtype=np.uint8), np.array([15, 255, 255], dtype=np.uint8))
            mask2 = cv2.inRange(hsv_roi_curr, np.array([150, 80, 40], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8))
            combined = cv2.bitwise_or(mask1, mask2)
            
            p_y = price_y_in_screen - chart_top if price_y_in_screen else roi_curr.shape[0] // 2
            p_y = max(0, min(p_y, roi_curr.shape[0] - 1))
            
            row_int = [combined[y, :].sum() // 255 for y in range(roi_curr.shape[0])]
            smoothed_curr = [int(np.mean(row_int[max(0, i-1):min(len(row_int), i+2)])) for i in range(len(row_int))]
            
            a_rows = smoothed_curr[:p_y]
            b_rows = smoothed_curr[p_y:]
            
            b_a_y = int(np.argmax(a_rows)) if a_rows else 0
            b_a_int = a_rows[b_a_y] if a_rows else 0
            
            b_b_y = p_y + int(np.argmax(b_rows)) if b_rows else roi_curr.shape[0] - 1
            b_b_int = b_rows[b_b_y - p_y] if b_rows else 0
            
            return b_a_y, b_a_int, b_b_y, b_b_int
            
        best_above_y, best_above_intensity, best_below_y, best_below_intensity = _get_intensity_zones()

        self._log(f"[Automator] [AdvCenter] Highest upper liquidity: ROI Y={best_above_y}, intensity={best_above_intensity}px")
        self._log(f"[Automator] [AdvCenter] Highest lower liquidity: ROI Y={best_below_y}, intensity={best_below_intensity}px")

        # ── Step 6: Zoom back in intelligently ───────────────────────────────
        self._log("[Automator] [AdvCenter] Step 6: Zooming in until upper zone (+3 boxes) and lower zone are fitted...")
        
        pyautogui.moveTo(price_axis_x, chart_cy, duration=0.1)
        time.sleep(0.1)
        
        # Iteratively zoom in until the distance between the padded top (best_above_y - 3*box_h)
        # and the padded bottom (best_below_y + 3*box_h) exceeds ~90% of the chart height.
        max_zoom_steps = 30
        for step_idx in range(max_zoom_steps):
            # Evaluate current distances
            a_y, _, b_y, _ = _get_intensity_zones()
            
            # Re-estimate box_h just in case scale changed dramatically, or use the fixed one
            padded_top = a_y - (3 * box_h)
            padded_bot = b_y + (3 * box_h)
            
            current_span = padded_bot - padded_top
            
            # If the span of our target region is larger than 90% of the screen, we stop zooming in
            if current_span >= chart_h * 0.90:
                self._log(f"[Automator] [AdvCenter] Target bounds reached (Span: {current_span}px vs Chart: {chart_h}px).")
                break
                
            # Scroll UP over price axis = zoom in (stretches axis)
            pyautogui.scroll(-120)  
            time.sleep(0.15) # Wait slightly longer for chart re-render
            
            if step_idx == max_zoom_steps - 1:
                self._log(f"[Automator] [AdvCenter] Reached max zoom-in steps.")
        
        time.sleep(1.0)

        # ── Step 7: Save analysis results ─────────────────────────────────────
        self._log("[Automator] [AdvCenter] Step 7: Saving analysis to learned_data...")
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(root_dir, "learned_data")
        os.makedirs(data_dir, exist_ok=True)
        out_path = os.path.join(data_dir, f"advanced_center_{pair_name}.txt")

        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(f"=== Advanced Center Analysis for {pair_name} ===\n")
            f.write(f"Captured at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Estimated grid box height : {box_h}px\n")
            f.write(f"Price line Y (screen)     : {price_y_in_screen}\n\n")
            f.write(f"--- UPPER HIGH LIQUIDITY ZONE ---\n")
            f.write(f"ROI row Y : {best_above_y}\n")
            f.write(f"Intensity : {best_above_intensity} high-liq pixels in that row\n\n")
            f.write(f"--- LOWER HIGH LIQUIDITY ZONE ---\n")
            f.write(f"ROI row Y : {best_below_y}\n")
            f.write(f"Intensity : {best_below_intensity} high-liq pixels in that row\n")

        self._log(f"[Automator] [AdvCenter] ✅ Analysis saved to {out_path}")
        self._log("[Automator] [AdvCenter] ✅ Advanced Center Chart complete.")
        return True

    # ─────────────────────────────────────────────────────────────
    # 7. Learn Liquidity Data (OCR tooltips)
    # ─────────────────────────────────────────────────────────────

    def learn_liquidity_data(self, pair_name, upper_blocks=5, lower_blocks=5):
        """
        Scan above and below the current price on the heatmap to read tooltips
        using OCR (pytesseract). Outputs to a text file for the Predictions tab.
        Order: Current price to Upper, then Current price to Lower.
        """
        try:
            import cv2
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        except ImportError:
            self._log("[Automator] [ERROR] cv2 and pytesseract are required for Learn Liquidity Data.")
            self._log("[Automator] Please run: pip install opencv-python pytesseract")
            self._log("[Automator] and ensure Tesseract-OCR is installed on Windows.")
            return False

        win = self.find_coinglass_window()
        if not win:
            self._log("[Automator] Cannot read liquidity – Coinglass window not found.")
            return False

        self._log("[Automator] Finding current price label to anchor the scan...")
        
        # 1. Detect current price center (reuse logic from center_chart_on_price)
        screenshot = pyautogui.screenshot()
        img_rgb = np.array(screenshot)
        img_bgr = img_rgb[:, :, ::-1]

        # Use a more constrained search area for the price axis
        axis_l = max(0, win.left + win.width - 120)
        axis_r = min(img_bgr.shape[1], win.left + win.width)
        axis_t = max(0, win.top + 50)
        # Avoid the very bottom of the window (taskbar/status bar noise)
        axis_b = min(img_bgr.shape[0], win.top + win.height - 100)

        roi = img_bgr[axis_t:axis_b, axis_l:axis_r]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # Save a debug image of what we're looking at
        cv2.imwrite("debug_liquidity_axis.png", roi)

        # Basic ranges for the price label (green/teal or red)
        hsv_ranges = [
            (np.array([35, 60, 60], dtype=np.uint8),  np.array([90, 255, 255], dtype=np.uint8)),
            (np.array([80, 60, 60], dtype=np.uint8),  np.array([100, 255, 255], dtype=np.uint8)),
            (np.array([25, 40, 40], dtype=np.uint8),  np.array([105, 255, 255], dtype=np.uint8)),
            (np.array([0, 60, 60], dtype=np.uint8),   np.array([10, 255, 255], dtype=np.uint8)),
            (np.array([160, 60, 60], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8)),
        ]

        best_contour = None
        best_area = 0

        for low, high in hsv_ranges:
            mask = cv2.inRange(hsv, low, high)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(largest)
                if area > best_area:
                    best_area = area
                    best_contour = largest

        if best_contour is None or best_area < 30:
            self._log("[Automator] Could not detect the price label to start scan.")
            return False

        bx, by, bw, bh = cv2.boundingRect(best_contour)
        price_screen_y = axis_t + by + bh // 2
        
        # User requested to click in the horizontal middle of the graph area.
        # axis_l is the right axis strip. win.left is the left edge of the window.
        # The center of the chart area is (win.left + axis_l) // 2
        scan_x = (win.left + axis_l) // 2
        
        self._log(f"[Automator] Liquidity scan X={scan_x} (chart center), Base Y={price_screen_y}")

        # Scan step configuration
        steps = 5
        px_per_step = 25
        
        above_data = []
        below_data = []
        
        # We need a custom pytesseract config to capture only digits/decimals/K/M. PSM 11 is "Sparse text. Find as much text as possible in no particular order" - good for grids
        custom_config = r'--oem 3 --psm 11'

        def click_and_read(y_pos):
            """Click a position on the heatmap and read the tooltip grid that appears."""
            import re
            
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            debug_dir = os.path.join(root_dir, "debug_tooltips")
            if not os.path.exists(debug_dir):
                os.makedirs(debug_dir)
            
            # 1. Take a BEFORE screenshot
            win_rect = (win.left, win.top, win.width, win.height)
            before_img = pyautogui.screenshot(region=win_rect)
            before_cv = cv2.cvtColor(np.array(before_img), cv2.COLOR_RGB2BGR)
            
            # 2. Click to trigger the tooltip grid
            pyautogui.moveTo(scan_x, y_pos, duration=0.1)
            pyautogui.click()
            time.sleep(2.0)
            
            # 3. Take an AFTER screenshot
            after_img = pyautogui.screenshot(region=win_rect)
            after_cv = cv2.cvtColor(np.array(after_img), cv2.COLOR_RGB2BGR)
            
            # 4. Compute absolute difference to isolate the newly-appearing grid
            diff = cv2.absdiff(before_cv, after_cv)
            diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            
            # Threshold the diff: anything that changed significantly
            _, diff_mask = cv2.threshold(diff_gray, 30, 255, cv2.THRESH_BINARY)
            
            # Dilate to join nearby changed pixels into solid regions
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
            diff_mask = cv2.dilate(diff_mask, kernel, iterations=3)
            
            # Find contours of the changed regions
            contours, _ = cv2.findContours(diff_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find the largest changed region (should be the tooltip grid)
            best_crop = None
            best_area = 0
            best_rect = None
            
            for c in contours:
                area = cv2.contourArea(c)
                if area < 5000:
                    continue
                rx, ry, rw, rh = cv2.boundingRect(c)
                # The grid should be reasonably sized
                if rw < 100 or rh < 50:
                    continue
                if area > best_area:
                    best_area = area
                    best_rect = (rx, ry, rw, rh)
            
            if best_rect:
                rx, ry, rw, rh = best_rect
                # Add some padding
                pad = 10
                y1 = max(0, ry - pad)
                y2 = min(after_cv.shape[0], ry + rh + pad)
                x1 = max(0, rx - pad)
                x2 = min(after_cv.shape[1], rx + rw + pad)
                best_crop = after_cv[y1:y2, x1:x2]
                self._log(f"[Automator] Detected tooltip grid at ({rx},{ry}) w={rw} h={rh}, diff_area={best_area}")
            else:
                self._log(f"[Automator] [WARN] No tooltip grid detected at Y={y_pos}. No significant change after click.")
                # Save debug image of the diff
                cv2.imwrite(os.path.join(debug_dir, f"diff_y{y_pos}.png"), diff_gray)
                return "No tooltip appeared"
            
            # 5. Preprocess for OCR
            gray = cv2.cvtColor(best_crop, cv2.COLOR_BGR2GRAY)
            # Upscale 3x for better OCR on small text
            gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            # Adaptive threshold works better on varying backgrounds
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY, 11, 2)
            
            # Save debug crops
            debug_path = os.path.join(debug_dir, f"table_y{y_pos}.png")
            cv2.imwrite(debug_path, thresh)
            
            # 6. OCR with PSM 6 (uniform block of text)
            text = pytesseract.image_to_string(thresh, config='--oem 3 --psm 6')
            self._log(f"[Automator] OCR raw (truncated): {text[:120].replace(chr(10), ' ')}")
            
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            # Parse: look for prices (e.g. 1.3720) and volumes (e.g. 1.4M, 394.0K)
            price_re = re.compile(r'\b\d{1,6}\.\d{1,5}\b')
            vol_re = re.compile(r'\b\d+(?:\.\d+)?\s*[KMBkmb]\b', re.IGNORECASE)
            
            all_prices = []
            all_volumes = []
            
            for line in lines:
                all_prices.extend(price_re.findall(line))
                all_volumes.extend(vol_re.findall(line))
            
            # Build a summary from what was found
            result_parts = []
            if all_prices:
                # Use the last price found (usually the row price label)
                result_parts.append(f"Price: {all_prices[-1]}")
            if all_volumes:
                def vol_to_val(v_str):
                    vs = v_str.upper().replace(' ', '')
                    if 'M' in vs: return float(vs.replace('M', '')) * 1_000_000
                    if 'K' in vs: return float(vs.replace('K', '')) * 1_000
                    if 'B' in vs: return float(vs.replace('B', '')) * 1_000_000_000
                    return 0
                sorted_vols = sorted(all_volumes, key=vol_to_val, reverse=True)
                result_parts.append(f"Vols: {', '.join(sorted_vols[:4])}")
            
            if result_parts:
                return " | ".join(result_parts)
            
            return "No readable grid data"

        self._log(f"[Automator] Scanning {upper_blocks} blocks ABOVE price (Current -> Upper)...")
        for i in range(1, upper_blocks + 1):
            if self._cancelled: return False
            y = price_screen_y - (i * px_per_step)
            res = click_and_read(y)
            above_data.append(f"Level +{i}: {res}")
            
        self._log(f"[Automator] Scanning {lower_blocks} blocks BELOW price (Current -> Lower)...")
        for i in range(1, lower_blocks + 1):
            if self._cancelled: return False
            y = price_screen_y + (i * px_per_step)
            res = click_and_read(y)
            below_data.append(f"Level -{i}: {res}")
            
        # Move mouse out of the way
        pyautogui.moveTo(win.left + 10, win.top + 10, duration=0.2)
        
        # Compile report
        report_lines = [
            f"=== Liquidity Data for {pair_name} ===",
            f"Captured at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "--- UPCOMMING LIQUIDITY (ABOVE PRICE) ---"
        ]
        # Reverse above_data so it reads top-to-bottom
        for line in reversed(above_data):
            report_lines.append(line)
            
        report_lines.extend([
            "",
            "--- LOWER LIQUIDITY (BELOW PRICE) ---"
        ])
        for line in below_data:
            report_lines.append(line)
            
        report_text = "\n".join(report_lines)
        
        # Write to file (use absolute path in a dedicated folder)
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(root_dir, "learned_data")
        os.makedirs(data_dir, exist_ok=True)
        
        file_path = os.path.join(data_dir, f"liquidity_data_{pair_name}.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
            
        self._log(f"[Automator] ✅ Liquidity data saved to {file_path}")
        return True
