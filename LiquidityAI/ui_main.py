import sys
import json
import os
import threading
try:
    import win32gui
    import win32con
    import win32api
except ImportError:
    win32gui = None

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QTextEdit, QFrame, QStackedWidget, QMessageBox, QDialog,
    QFormLayout, QDialogButtonBox, QCheckBox, QFileDialog, QSpinBox, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot, QObject
from PyQt5.QtGui import QFont, QColor, QPixmap

from modules.bot_worker import BotWorker
from modules.coinglass_automator import CoinglassAutomator
from modules.trade_tracker import TradeTracker
from modules.screen_recorder import ScreenRecorderWorker
from ui_macro_builder import MacroBuilderDialog, GlobalMacroManagerDialog, load_global_macros, ScreenOverlay


class _Signals(QObject):
    """Thread-safe signal bridge for automator callbacks."""
    log = pyqtSignal(str)
    hotkey_pressed = pyqtSignal()


class GlobalHotkeyThread(threading.Thread):
    def __init__(self, signals):
        super().__init__(daemon=True)
        self.signals = signals

    def run(self):
        if not win32gui:
            return
        
        # Register F2 (0x71) as a global hotkey with ID 1
        # No modifiers (0)
        try:
            if not win32gui.RegisterHotKey(None, 1, 0, win32con.VK_F2):
                print("[Hotkey] Failed to register F2 hotkey.")
                return

            try:
                msg = win32gui.GetMessage(None, 0, 0)
                while msg:
                    if msg[1] == win32con.WM_HOTKEY:
                        if msg[2] == 1: # ID 1 = F2
                            self.signals.hotkey_pressed.emit()
                    msg = win32gui.GetMessage(None, 0, 0)
            finally:
                win32gui.UnregisterHotKey(None, 1)
        except Exception as e:
            print(f"[Hotkey] Error in hotkey thread: {e}")


class LiquidityUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LiquidityAI Desktop")
        self.setGeometry(100, 100, 1200, 800)

        self.pairs_file = "pairs.json"
        self.configured_pairs = self.load_pairs()
        self.active_bots = {}        # pair -> BotWorker
        self.active_automators = {}  # pair -> CoinglassAutomator (running in bg thread)
        self.current_selected_pair = None
        self.tracker = TradeTracker()
        self._pair_buttons = {}      # pair -> {'toggle': QPushButton}
        self._bot_state    = {}      # pair -> 'start' | 'pause' | 'resume'  (source of truth)

        self._sig = _Signals()
        self._sig.log.connect(self._append_log)
        self._sig.hotkey_pressed.connect(self.stop_all_bots)

        self.init_ui()
        
        if win32gui:
            self.hotkey_thread = GlobalHotkeyThread(self._sig)
            self.hotkey_thread.start()
        else:
            self._append_log("[UI] [WARN] pywin32 not found. F2 global stop button will not work.")

    # ── Persistence ──────────────────────────────────────────────
    def load_pairs(self):
        if os.path.exists(self.pairs_file):
            with open(self.pairs_file, 'r') as f:
                data = json.load(f)
            result = []
            for item in data:
                if isinstance(item, str):
                    # Migrate old plain string
                    result.append({'name': item, 'slider_img': '',
                                   'set_slider_min': True, 'set_slider_max': True})
                else:
                    # Ensure new keys exist (backward compat with numeric format)
                    item.setdefault('slider_img', '')
                    item.setdefault('set_slider_min', True)
                    item.setdefault('set_slider_max', True)
                    result.append(item)
            return result
        return []

    def save_pairs(self):
        with open(self.pairs_file, 'w') as f:
            json.dump(self.configured_pairs, f, indent=4)

    def _pair_names(self):
        return [p['name'] for p in self.configured_pairs]

    # ── Build UI ─────────────────────────────────────────────────
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # ─── Sidebar ───
        sidebar = QFrame()
        sidebar.setFrameShape(QFrame.StyledPanel)
        sidebar.setFixedWidth(200)
        sl = QVBoxLayout(sidebar)

        title = QLabel("LiquidityAI")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        sl.addWidget(title)
        
        btn_dash = QPushButton("Dashboard")
        btn_set = QPushButton("Settings")
        btn_macros = QPushButton("Manage Global Macros")
        
        sl.addWidget(btn_dash)
        sl.addWidget(btn_set)
        sl.addWidget(btn_macros)
        sl.addStretch()

        btn_macros.clicked.connect(self.open_global_macros)

        # ─── Stacked content ───
        content = QWidget()
        cl = QVBoxLayout(content)
        self.stack = QStackedWidget()
        cl.addWidget(self.stack)

        # ── Dashboard ──
        dash = QWidget()
        dl = QVBoxLayout(dash)

        # Add pair bar
        add_bar = QHBoxLayout()
        self.txt_pair = QLineEdit()
        self.txt_pair.setPlaceholderText("Enter pair (e.g. XRPUSDT)")
        btn_add = QPushButton("Add Pair")
        btn_add.clicked.connect(self.add_pair)
        add_bar.addWidget(QLabel("New Pair:"))
        add_bar.addWidget(self.txt_pair)
        add_bar.addWidget(btn_add)
        dl.addLayout(add_bar)

        splitter = QSplitter(Qt.Horizontal)

        # Left: pairs list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Configured Pairs", font=QFont("Arial", 12, QFont.Bold)))
        self.list_pairs = QListWidget()
        self.list_pairs.itemClicked.connect(self.on_pair_selected)
        self.populate_pairs_list()
        ll.addWidget(self.list_pairs)

        # Right: details
        right = QWidget()
        rl = QVBoxLayout(right)

        self.lbl_pair = QLabel("Select a pair from the list")
        self.lbl_pair.setFont(QFont("Arial", 14, QFont.Bold))
        rl.addWidget(self.lbl_pair)

        stats = QHBoxLayout()
        self.lbl_total = QLabel("Total Predictions: 0")
        self.lbl_wr = QLabel("Win Rate: 0%")
        self.lbl_lr = QLabel("Loss Rate: 0%")
        stats.addWidget(self.lbl_total)
        stats.addWidget(self.lbl_wr)
        stats.addWidget(self.lbl_lr)
        rl.addLayout(stats)

        self.tabs = QTabWidget()

        # Logs tab
        self.tab_logs = QWidget()
        tll = QVBoxLayout(self.tab_logs)

        # Clear log button row
        log_toolbar = QHBoxLayout()
        btn_clear_log = QPushButton("Clear Log")
        btn_clear_log.setFixedWidth(90)
        btn_clear_log.clicked.connect(lambda: self.txt_logs.clear())
        log_toolbar.addStretch()
        log_toolbar.addWidget(btn_clear_log)
        tll.addLayout(log_toolbar)

        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        tll.addWidget(self.txt_logs)
        self.tabs.addTab(self.tab_logs, "Logs")

        # Predictions tab
        self.tab_preds = QWidget()
        tpl = QVBoxLayout(self.tab_preds)
        
        # Splitter to separate table and liquidity data
        pred_splitter = QSplitter(Qt.Vertical)
        
        # Table
        self.table_preds = QTableWidget(0, 5)
        self.table_preds.setHorizontalHeaderLabels(["Time", "Price", "Direction", "TP", "SL"])
        self.table_preds.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        pred_splitter.addWidget(self.table_preds)
        
        # Liquidity Data Display
        liq_container = QWidget()
        liql = QVBoxLayout(liq_container)
        liql.setContentsMargins(0, 0, 0, 0)
        liql.addWidget(QLabel("<b>Liquidity Data (From heatmaps)</b>"))
        self.txt_liquidity = QTextEdit()
        self.txt_liquidity.setReadOnly(True)
        self.txt_liquidity.setPlaceholderText("Liquidity learned from charts will appear here...")
        liql.addWidget(self.txt_liquidity)
        
        pred_splitter.addWidget(liq_container)
        pred_splitter.setSizes([400, 200])
        
        tpl.addWidget(pred_splitter)
        self.tabs.addTab(self.tab_preds, "Predictions")

        rl.addWidget(self.tabs)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([360, 600])
        dl.addWidget(splitter)
        self.stack.addWidget(dash)

        # ── Settings ──
        settings = QWidget()
        setl = QVBoxLayout(settings)
        setl.addWidget(QLabel("Global Settings", font=QFont("Arial", 16, QFont.Bold)))

        self.btn_rec_start = QPushButton("Start Screen Recording")
        self.btn_rec_stop = QPushButton("Stop Screen Recording")
        self.btn_rec_stop.setEnabled(False)
        self.btn_rec_start.clicked.connect(self.start_recording)
        self.btn_rec_stop.clicked.connect(self.stop_recording)
        setl.addWidget(QLabel("Record your trading session to review AI predictions."))
        setl.addWidget(self.btn_rec_start)
        setl.addWidget(self.btn_rec_stop)
        setl.addStretch()
        self.stack.addWidget(settings)

        btn_dash.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        btn_set.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        root.addWidget(sidebar)
        root.addWidget(content)

        self.screen_recorder = None

    def open_global_macros(self):
        diag = GlobalMacroManagerDialog(self)
        diag.exec_()
        self.populate_pairs_list() # refresh dropdowns if modified

    # ── Pairs list ───────────────────────────────────────────────
    def populate_pairs_list(self):
        self.list_pairs.clear()
        for pair_cfg in self.configured_pairs:
            pair = pair_cfg['name']
            item = QListWidgetItem()
            w = self._pair_row(pair_cfg)
            item.setSizeHint(w.sizeHint())
            item.setData(Qt.UserRole, pair)
            self.list_pairs.addItem(item)
            self.list_pairs.setItemWidget(item, w)

    # ── Button state constants ────────────────────────────────────
    _BTN_START  = 'start'
    _BTN_PAUSE  = 'pause'
    _BTN_RESUME = 'resume'

    _BTN_STYLES = {
        'start':  ("▶ Start",  "QPushButton{background:#1a6b2a;color:white;border-radius:3px;font-weight:bold;}QPushButton:hover{background:#22882e;}"),
        'pause':  ("⏸ Pause",  "QPushButton{background:#7a5c00;color:white;border-radius:3px;font-weight:bold;}QPushButton:hover{background:#a07800;}"),
        'resume': ("▶ Resume", "QPushButton{background:#1a4a7a;color:white;border-radius:3px;font-weight:bold;}QPushButton:hover{background:#1e5fa0;}"),
    }

    def _set_btn_state(self, pair, state):
        """Switch the toggle button for `pair` to state: 'start' | 'pause' | 'resume'."""
        self._bot_state[pair] = state          # update Python-side state first
        if pair not in self._pair_buttons:
            return
        btn = self._pair_buttons[pair]['toggle']
        text, style = self._BTN_STYLES[state]
        btn.setText(text)
        btn.setStyleSheet(style)

    def _pair_row(self, pair_cfg):
        """One row: name | [⚙ Settings] | [▶ Start/⏸Pause/▶Resume] | [⏹] | [🗑]"""
        pair = pair_cfg['name']
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 3, 4, 3)
        h.setSpacing(4)

        lbl = QLabel(pair)
        lbl.setFont(QFont("Arial", 9, QFont.Bold))
        lbl.setMinimumWidth(80)

        # ── Gear / settings button ──
        btn_settings = QPushButton("⚙")
        btn_settings.setFixedWidth(28)
        btn_settings.setToolTip(f"Slider settings for {pair}")
        btn_settings.setStyleSheet(
            "QPushButton{background:#2a2a3a;color:#aaaacc;border:1px solid #444;border-radius:3px;font-size:14px;}"
            "QPushButton:hover{background:#3a3a5a;color:white;}"
        )

        # ── Control buttons ──
        btn_toggle = QPushButton("\u25b6 Start")
        btn_toggle.setFixedWidth(75)
        btn_toggle.setStyleSheet(self._BTN_STYLES['start'][1])
        btn_toggle.setProperty('state', 'start')

        btn_stop   = QPushButton("\u23f9")
        btn_delete = QPushButton("\U0001f5d1")
        btn_stop.setFixedWidth(30)
        btn_delete.setFixedWidth(30)

        btn_stop.setStyleSheet(
            "QPushButton{background:#5a2020;color:white;border-radius:3px;}"
            "QPushButton:hover{background:#7a2a2a;}"
        )
        btn_delete.setStyleSheet(
            "QPushButton{background:#3a1212;color:#ff6b6b;border:1px solid #ff6b6b;border-radius:3px;font-size:13px;}"
            "QPushButton:hover{background:#8b0000;color:white;}"
        )

        btn_toggle.setToolTip(f"Start / Pause bot for {pair}")
        btn_stop.setToolTip(f"Stop bot for {pair}")
        btn_delete.setToolTip(f"Remove {pair} from list")

        self._pair_buttons[pair] = {'toggle': btn_toggle, 'stop': btn_stop}
        self._bot_state[pair] = 'start'

        def on_toggle(_, p=pair):
            state = self._bot_state.get(p, 'start')
            if state in ('start', 'resume'):
                self.start_bot(p)
            elif state == 'pause':
                self.pause_bot(p)

        btn_settings.clicked.connect(lambda _, p=pair: self._open_pair_settings(p))
        btn_toggle.clicked.connect(on_toggle)
        btn_stop.clicked.connect(lambda _, p=pair: self.stop_bot(p))
        btn_delete.clicked.connect(lambda _, p=pair: self.delete_pair(p))

        h.addWidget(lbl)
        h.addStretch()
        h.addWidget(btn_settings)
        h.addWidget(btn_toggle)
        h.addWidget(btn_stop)
        h.addWidget(btn_delete)
        return w

    def _open_pair_settings(self, pair):
        """
        Open the settings dialog for the selected pair.
        Two independent sections:
          1. Custom Macros (always visible, multi-select)
          2. Hardcoded Search Process (toggle + slider settings)
        """
        from ui_macro_builder import ScreenOverlay

        cfg = next((p for p in self.configured_pairs if p['name'] == pair), None)
        if not cfg:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Settings for {pair}")
        dialog.setMinimumWidth(450)
        layout = QVBoxLayout(dialog)

        # ═══════════════════════════════════════════════════════════
        # SECTION 1: Custom Macros (always visible)
        # ═══════════════════════════════════════════════════════════
        lbl_macros = QLabel("<b>Custom Automation Macros</b>")
        layout.addWidget(lbl_macros)
        layout.addWidget(QLabel("<i>Select one or more macros to run for this pair. "
                                "They will execute in order.</i>"))

        macro_list_container = QWidget()
        macro_vbox = QVBoxLayout(macro_list_container)
        macro_vbox.setContentsMargins(0, 0, 0, 0)
        macro_vbox.setSpacing(4)

        macros = load_global_macros()
        selected_macros = cfg.get('macro_names', [])
        macro_runs = cfg.get('macro_runs', {})  # {name: count}  0 = unlimited
        # Backward compat
        if not selected_macros and cfg.get('macro_name'):
            selected_macros = [cfg['macro_name']]

        macro_widgets = []  # [(checkbox, name, spinbox)]

        for m in sorted(macros.keys()):
            row_w = QWidget()
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(4, 2, 4, 2)
            row_h.setSpacing(6)

            chk = QCheckBox(f"{m}  ({len(macros[m])} steps)")
            chk.setChecked(m in selected_macros)
            chk.setStyleSheet("QCheckBox { color: #eee; }")

            lbl_runs = QLabel("Runs:")
            lbl_runs.setStyleSheet("color: #aaa; font-size: 11px;")

            spin_runs = QSpinBox()
            spin_runs.setRange(0, 9999)
            spin_runs.setValue(macro_runs.get(m, 1))
            spin_runs.setSpecialValueText("∞")  # 0 displays as ∞ (unlimited)
            spin_runs.setFixedWidth(65)
            spin_runs.setToolTip("0 = unlimited, 1 = run once (default)")
            spin_runs.setStyleSheet(
                "QSpinBox { background: #1e1e1e; color: #8be9fd; border: 1px solid #555; "
                "border-radius: 3px; padding: 2px; }"
            )

            row_h.addWidget(chk)
            row_h.addStretch()
            row_h.addWidget(lbl_runs)
            row_h.addWidget(spin_runs)

            macro_vbox.addWidget(row_w)
            macro_widgets.append((chk, m, spin_runs))

        if not macros:
            macro_vbox.addWidget(QLabel("<i>No global macros created yet.</i>"))

        scroll_area = QWidget()
        scroll_area.setLayout(QVBoxLayout())
        scroll_area.layout().setContentsMargins(0, 0, 0, 0)
        scroll_area.layout().addWidget(macro_list_container)
        scroll_area.setStyleSheet("background: #1e1e1e; border: 1px solid #555; border-radius: 3px;")
        scroll_area.setMaximumHeight(150)
        layout.addWidget(scroll_area)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #555;")
        layout.addWidget(sep)

        # ═══════════════════════════════════════════════════════════
        # SECTION 2: Hardcoded Search Process (toggle + settings)
        # ═══════════════════════════════════════════════════════════
        chk_hardcoded = QCheckBox("Enable Default Hardcoded Search Process")
        chk_hardcoded.setChecked(cfg.get('use_hardcoded_search', False))
        chk_hardcoded.setStyleSheet("QCheckBox{font-weight:bold;font-size:12px;}")
        layout.addWidget(chk_hardcoded)
        layout.addWidget(QLabel("<i>When enabled, the bot will automatically type the coin name, "
                                "search, and interact with the slider.</i>"))

        # Container for slider settings
        hc_container = QWidget()
        hc_layout = QVBoxLayout(hc_container)
        hc_layout.setContentsMargins(0, 8, 0, 0)

        # --- Slider Image ---
        form = QFormLayout()
        btn_img = QPushButton("Browse...")
        lbl_img = QLabel(os.path.basename(cfg.get('slider_img', 'None selected')) if cfg.get('slider_img') else 'None selected')
        def browse():
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Slider Image", "", "Images (*.png *.jpg)")
            if path:
                cfg['slider_img'] = path
                lbl_img.setText(os.path.basename(path))
        btn_img.clicked.connect(browse)

        img_box = QHBoxLayout()
        img_box.addWidget(lbl_img)
        img_box.addWidget(btn_img)
        form.addRow("Slider Image:", img_box)
        hc_layout.addLayout(form)

        # --- Min Click Capture ---
        chk_min = QCheckBox("Set Slider Min")
        chk_min.setChecked(cfg.get('set_slider_min', True))

        min_x_val = cfg.get('min_click_x', '')
        min_y_val = cfg.get('min_click_y', '')
        lbl_min_coords = QLabel(f"({min_x_val}, {min_y_val})" if min_x_val != '' else "Not set")
        lbl_min_coords.setStyleSheet("color:#8be9fd; font-weight:bold;")

        btn_capture_min = QPushButton("📍 Capture Min Click")
        btn_capture_min.setStyleSheet(
            "QPushButton{background:#2a3a4a;color:#8be9fd;border:1px solid #446;border-radius:3px;padding:5px;}"
            "QPushButton:hover{background:#3a5a7a;}"
        )

        def capture_min():
            dialog.showMinimized()
            self.showMinimized()
            overlay = ScreenOverlay(capture_mode='click')
            overlay._pair_settings_dialog = dialog  # prevent GC

            def on_captured(x, y):
                from PyQt5.QtCore import QTimer
                def restore():
                    self.showNormal()
                    dialog.showNormal()
                    dialog.raise_()
                    dialog.activateWindow()
                    lbl_min_coords.setText(f"({x}, {y})")
                    lbl_min_coords.setProperty('captured_x', x)
                    lbl_min_coords.setProperty('captured_y', y)
                QTimer.singleShot(100, restore)

            def on_cancelled():
                self.showNormal()
                dialog.showNormal()
                dialog.raise_()

            overlay.captured_click.connect(on_captured)
            overlay.cancelled.connect(on_cancelled)
            overlay.show()
            dialog._overlay = overlay  # prevent GC

        btn_capture_min.clicked.connect(capture_min)

        min_row = QHBoxLayout()
        min_row.addWidget(chk_min)
        min_row.addStretch()
        min_row.addWidget(lbl_min_coords)
        min_row.addWidget(btn_capture_min)
        hc_layout.addLayout(min_row)

        # --- Max Click Capture ---
        chk_max = QCheckBox("Set Slider Max")
        chk_max.setChecked(cfg.get('set_slider_max', True))

        max_x_val = cfg.get('max_click_x', '')
        max_y_val = cfg.get('max_click_y', '')
        lbl_max_coords = QLabel(f"({max_x_val}, {max_y_val})" if max_x_val != '' else "Not set")
        lbl_max_coords.setStyleSheet("color:#ff79c6; font-weight:bold;")

        btn_capture_max = QPushButton("📍 Capture Max Click")
        btn_capture_max.setStyleSheet(
            "QPushButton{background:#4a2a3a;color:#ff79c6;border:1px solid #644;border-radius:3px;padding:5px;}"
            "QPushButton:hover{background:#7a3a5a;}"
        )

        def capture_max():
            dialog.showMinimized()
            self.showMinimized()
            overlay = ScreenOverlay(capture_mode='click')

            def on_captured(x, y):
                from PyQt5.QtCore import QTimer
                def restore():
                    self.showNormal()
                    dialog.showNormal()
                    dialog.raise_()
                    dialog.activateWindow()
                    lbl_max_coords.setText(f"({x}, {y})")
                    lbl_max_coords.setProperty('captured_x', x)
                    lbl_max_coords.setProperty('captured_y', y)
                QTimer.singleShot(100, restore)

            def on_cancelled():
                self.showNormal()
                dialog.showNormal()
                dialog.raise_()

            overlay.captured_click.connect(on_captured)
            overlay.cancelled.connect(on_cancelled)
            overlay.show()
            dialog._overlay = overlay

        btn_capture_max.clicked.connect(capture_max)

        max_row = QHBoxLayout()
        max_row.addWidget(chk_max)
        max_row.addStretch()
        max_row.addWidget(lbl_max_coords)
        max_row.addWidget(btn_capture_max)
        hc_layout.addLayout(max_row)

        layout.addWidget(hc_container)

        # Toggle visibility based on checkbox
        hc_container.setVisible(chk_hardcoded.isChecked())
        chk_hardcoded.toggled.connect(hc_container.setVisible)

        # ── OK / Cancel ──
        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(dialog.accept)
        bbox.rejected.connect(dialog.reject)
        layout.addWidget(bbox)

        if dialog.exec_():
            # Save checked macros and run counts
            selected = []
            run_counts = {}
            for chk, mname, spin in macro_widgets:
                if chk.isChecked():
                    selected.append(mname)
                run_counts[mname] = spin.value()
            cfg['macro_names'] = selected
            cfg['macro_runs'] = run_counts
            cfg['macro_name'] = selected[0] if selected else ""  # backward compat

            cfg['use_hardcoded_search'] = chk_hardcoded.isChecked()
            cfg['set_slider_min'] = chk_min.isChecked()
            cfg['set_slider_max'] = chk_max.isChecked()

            # Save captured min coordinates
            min_cx = lbl_min_coords.property('captured_x')
            min_cy = lbl_min_coords.property('captured_y')
            if min_cx is not None:
                cfg['min_click_x'] = min_cx
                cfg['min_click_y'] = min_cy

            # Save captured max coordinates
            max_cx = lbl_max_coords.property('captured_x')
            max_cy = lbl_max_coords.property('captured_y')
            if max_cx is not None:
                cfg['max_click_x'] = max_cx
                cfg['max_click_y'] = max_cy

            cfg.pop('macro_steps', None)

            self.save_pairs()
            self._append_log(f"[UI] Settings saved for {pair}.")

    # ── Pair CRUD ─────────────────────────────────────────────────
    def add_pair(self):
        pair = self.txt_pair.text().strip().upper()
        if not pair:
            return
        if pair in self._pair_names():
            self._append_log(f"[UI] '{pair}' already in list.")
            return
        self.configured_pairs.append({'name': pair, 'slider_img': '',
                                       'set_slider_min': True, 'set_slider_max': True})
        self.save_pairs()
        self.populate_pairs_list()
        self.txt_pair.clear()
        self._append_log(f"[UI] Added pair: {pair}")

    def delete_pair(self, pair):
        if pair in self.active_bots:
            reply = QMessageBox.question(
                self, "Bot Running",
                f"'{pair}' has an active bot. Stop it and delete?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            self.stop_bot(pair)

        self.configured_pairs = [p for p in self.configured_pairs if p['name'] != pair]
        self.save_pairs()
        self.populate_pairs_list()
        self._append_log(f"[UI] Deleted pair: {pair}")
        if self.current_selected_pair == pair:
            self.current_selected_pair = None
            self.lbl_pair.setText("Select a pair from the list")

    def on_pair_selected(self, item):
        pair = item.data(Qt.UserRole)
        self.current_selected_pair = pair
        self.lbl_pair.setText(f"Active Pair: {pair}")
        self.txt_logs.clear()
        self.table_preds.setRowCount(0)
        self.txt_liquidity.clear()
        self.update_stats()
        self.refresh_liquidity_display(pair)
        
    def refresh_liquidity_display(self, pair):
        """Load the liquidity text file for the given pair if it exists."""
        if not pair: return
        # Use absolute path relative to the app directory
        app_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(app_dir, "learned_data", f"liquidity_data_{pair}.txt")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.txt_liquidity.setPlainText(f.read())
            except Exception as e:
                self._append_log(f"[UI] Error reading liquidity file: {e}")
        else:
            self.txt_liquidity.clear()
            self.txt_liquidity.setPlaceholderText(f"No liquidity data learned yet for {pair}...")

    def update_stats(self):
        if not self.current_selected_pair:
            return
        s = self.tracker.get_stats(self.current_selected_pair)
        self.lbl_total.setText(f"Total Predictions: {s['total_predictions']}")
        self.lbl_wr.setText(f"Win Rate: {s['win_rate']}%")
        self.lbl_lr.setText(f"Loss Rate: {s['loss_rate']}%")

    # ── Logging ──────────────────────────────────────────────────
    @pyqtSlot(str)
    def _append_log(self, msg):
        self.txt_logs.append(msg)
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )
        self.tabs.setCurrentWidget(self.tab_logs)

    # ── Bot management ───────────────────────────────────────────
    def start_bot(self, pair):
        # ── Resume if already paused ──
        if pair in self.active_bots:
            w = self.active_bots[pair]
            if w.is_paused:
                w.resume()
                self._set_btn_state(pair, self._BTN_PAUSE)  # now running → show Pause
                self._append_log(f"[UI] Resumed bot for {pair}.")
            else:
                self._append_log(f"[UI] Bot for {pair} is already running.")
            return

        if pair in self.active_automators:
            self._append_log(f"[UI] Automation for {pair} is already in progress.")
            return

        # ── Stop ALL other running bots/automators first ──
        other_pairs = [p for p in list(self.active_bots.keys()) + list(self.active_automators.keys()) if p != pair]
        if other_pairs:
            self._append_log(f"[UI] Stopping other pairs before starting {pair}...")
            for p in set(other_pairs):
                self.stop_bot(p)

        self.current_selected_pair = pair
        self.lbl_pair.setText(f"Active Pair: {pair}")
        self._append_log(f"[UI] Starting Coinglass automation for {pair}...")
        # Show as running immediately so user gets feedback
        self._set_btn_state(pair, self._BTN_PAUSE)

        config = {}
        if os.path.exists("config.json"):
            with open("config.json") as f:
                config = json.load(f)

        # Attach per-pair slider image settings to config
        pair_cfg = next((p for p in self.configured_pairs if p['name'] == pair), {})
        config['slider_img']      = pair_cfg.get('slider_img', '')
        config['set_slider_min']  = pair_cfg.get('set_slider_min', True)
        config['set_slider_max']  = pair_cfg.get('set_slider_max', True)
        config['slider_y_offset'] = pair_cfg.get('slider_y_offset', 0)
        config['use_hardcoded_search'] = pair_cfg.get('use_hardcoded_search', False)
        
        if pair_cfg.get('slider_click_y') is not None:
            config['slider_click_y'] = pair_cfg['slider_click_y']

        # Per-handle captured click coordinates
        for key in ('min_click_x', 'min_click_y', 'max_click_x', 'max_click_y'):
            if pair_cfg.get(key) is not None:
                config[key] = pair_cfg[key]

        def log_cb(msg):
            self._sig.log.emit(msg)

        automator = CoinglassAutomator(config=config, log_callback=log_cb)
        self.active_automators[pair] = automator

        def run():
            # Collect all selected macro steps
            macro_names = pair_cfg.get('macro_names', [])
            macro_runs = pair_cfg.get('macro_runs', {})  # {name: count}  0=unlimited
            # Backward compat: fall back to old single key
            if not macro_names and pair_cfg.get('macro_name'):
                macro_names = [pair_cfg['macro_name']]

            all_macros = load_global_macros()
            ok = True

            # Execute selected macros in order, each repeated per its run count
            for mname in macro_names:
                if automator._cancelled:
                    break
                steps = all_macros.get(mname, [])
                if not steps:
                    continue
                count = macro_runs.get(mname, 1)
                if count == 0:
                    # Unlimited — loop until cancelled or failure
                    iteration = 1
                    while not automator._cancelled:
                        log_cb(f"[UI] Running macro: {mname} (loop #{iteration})")
                        ok = automator.execute_macro(pair, steps)
                        if not ok:
                            break
                        iteration += 1
                else:
                    for i in range(count):
                        if automator._cancelled:
                            break
                        suffix = f" ({i+1}/{count})" if count > 1 else ""
                        log_cb(f"[UI] Running macro: {mname}{suffix} ({len(steps)} steps)")
                        ok = automator.execute_macro(pair, steps)
                        if not ok:
                            break
                if not ok:
                    break

            # Then run hardcoded search if enabled (and macros succeeded)
            if ok and not automator._cancelled and config['use_hardcoded_search']:
                ok = automator.search_and_select_pair(pair, exchange="Binance")
            elif ok and not automator._cancelled and not macro_names:
                log_cb(f"[UI] No macros selected and hardcoded search disabled. Proceeding directly.")

            self.active_automators.pop(pair, None)
            if ok and not automator._cancelled:
                log_cb(f"[UI] Coinglass ready. Launching bot for {pair}...")
                # Refresh liquidity text on the main thread before starting the bot
                QTimer.singleShot(0, lambda: self.refresh_liquidity_display(pair))
                QTimer.singleShot(0, lambda: self._launch_bot(pair))
            else:
                if not automator._cancelled:
                    log_cb(f"[UI] Coinglass automation failed. Bot NOT started for {pair}.")
                    QTimer.singleShot(0, lambda: self._set_btn_state(pair, self._BTN_START))

        threading.Thread(target=run, daemon=True).start()

    def _launch_bot(self, pair):
        w = BotWorker(pair, mode='predict')
        w.log_msg.connect(self.on_log_msg)
        w.prediction_made.connect(self.on_prediction)
        w.bot_stopped.connect(lambda: self.on_bot_stopped(pair))
        self.active_bots[pair] = w
        w.start()

    def pause_bot(self, pair):
        # If still in automation phase, cancel it
        if pair in self.active_automators:
            self.active_automators[pair].cancel()
            self.active_automators.pop(pair, None)
            self._append_log(f"[UI] Cancelled automation for {pair}.")
            self._set_btn_state(pair, self._BTN_START)
            return
        # If bot is running, pause it
        if pair in self.active_bots:
            self.active_bots[pair].pause()
            self._set_btn_state(pair, self._BTN_RESUME)
            self._append_log(f"[UI] Paused bot for {pair}.")
            return
        # Pair not found in either dict (timing gap or already stopped)
        self._append_log(f"[UI] Nothing to pause for {pair}.")
        self._set_btn_state(pair, self._BTN_START)

    def stop_bot(self, pair):
        # Cancel automation thread if still searching
        if pair in self.active_automators:
            self.active_automators[pair].cancel()
            self.active_automators.pop(pair, None)
            self._append_log(f"[UI] Stopped automation for {pair}.")
        # Stop the bot worker if running
        if pair in self.active_bots:
            self.active_bots[pair].stop()
        self._set_btn_state(pair, self._BTN_START)  # back to Start

    def stop_all_bots(self):
        """Global stop for everything."""
        self._append_log("[UI] [ACTION] F2 Pressed: Stopping all active bots and automation...")
        
        # Stop automators
        for pair in list(self.active_automators.keys()):
            automator = self.active_automators.get(pair)
            if automator:
                automator.cancel()
        self.active_automators.clear()
        
        # Stop bots
        for pair in list(self.active_bots.keys()):
            worker = self.active_bots.get(pair)
            if worker:
                worker.stop()
        
        # UI state will be reset via the lambda connects or here for certainty
        for p_cfg in self.configured_pairs:
            self._set_btn_state(p_cfg['name'], self._BTN_START)

    @pyqtSlot(str)
    def on_log_msg(self, msg):
        s = self.sender()
        if s and self.current_selected_pair == s.pair:
            self._append_log(msg)

    @pyqtSlot(dict)
    def on_prediction(self, data):
        s = self.sender()
        if not (s and self.current_selected_pair == s.pair):
            return
        row = self.table_preds.rowCount()
        self.table_preds.insertRow(row)
        self.table_preds.setItem(row, 0, QTableWidgetItem(data.get('time', '')))
        self.table_preds.setItem(row, 1, QTableWidgetItem(f"{data.get('current_price', 0):.4f}"))
        direction = data.get('direction', '')
        di = QTableWidgetItem(direction)
        if direction == "UP":
            di.setForeground(QColor("lime"))
        elif direction == "DOWN":
            di.setForeground(QColor("red"))
        self.table_preds.setItem(row, 2, di)
        tp = data.get('target_price', 0)
        sl = data.get('stop_loss', 0)
        self.table_preds.setItem(row, 3, QTableWidgetItem(f"{tp:.4f}"))
        self.table_preds.setItem(row, 4, QTableWidgetItem(f"{sl:.4f}"))
        price = data.get('current_price', 0)
        self.tracker.update_prices(s.pair, price)
        if direction != "NEUTRAL":
            self.tracker.add_trade(s.pair, direction, price, tp, sl)
        self.update_stats()

    def on_bot_stopped(self, pair):
        self.active_bots.pop(pair, None)
        self._set_btn_state(pair, self._BTN_START)  # reset button when bot exits
        if self.current_selected_pair == pair:
            self._append_log(f"--- Bot stopped for {pair} ---")

    # ── Recording ────────────────────────────────────────────────
    def start_recording(self):
        self.screen_recorder = ScreenRecorderWorker()
        self.screen_recorder.recording_stopped.connect(self.on_recording_stopped)
        self.screen_recorder.start()
        self.btn_rec_start.setEnabled(False)
        self.btn_rec_stop.setEnabled(True)

    def stop_recording(self):
        if self.screen_recorder:
            self.screen_recorder.stop_recording()

    def on_recording_stopped(self):
        self.btn_rec_start.setEnabled(True)
        self.btn_rec_stop.setEnabled(False)
        self.screen_recorder = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    p = app.palette()
    p.setColor(p.Window,          QColor(53, 53, 53))
    p.setColor(p.WindowText,      Qt.white)
    p.setColor(p.Base,            QColor(25, 25, 25))
    p.setColor(p.AlternateBase,   QColor(53, 53, 53))
    p.setColor(p.ToolTipBase,     Qt.white)
    p.setColor(p.ToolTipText,     Qt.white)
    p.setColor(p.Text,            Qt.white)
    p.setColor(p.Button,          QColor(53, 53, 53))
    p.setColor(p.ButtonText,      Qt.white)
    p.setColor(p.BrightText,      Qt.red)
    p.setColor(p.Link,            QColor(42, 130, 218))
    p.setColor(p.Highlight,       QColor(42, 130, 218))
    p.setColor(p.HighlightedText, Qt.black)
    app.setPalette(p)

    window = LiquidityUI()
    window.show()
    sys.exit(app.exec_())
