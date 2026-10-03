import sys
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QInputDialog, QMessageBox, QWidget,
    QComboBox, QSpinBox, QDoubleSpinBox, QApplication, QFileDialog, QRadioButton,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen

import os
import json

MACROS_FILE = "macros.json"

def load_global_macros():
    if os.path.exists(MACROS_FILE):
        try:
            with open(MACROS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_global_macros(macros):
    with open(MACROS_FILE, "w") as f:
        json.dump(macros, f, indent=4)

class ScreenOverlay(QWidget):
    """
    A transparent full-screen overlay to capture mouse clicks or swipes.
    Emits (x, y) for clicks, or (start_x, start_y, end_x, end_y) for swipes.
    """
    captured_click = pyqtSignal(int, int)
    captured_swipe = pyqtSignal(int, int, int, int)
    cancelled = pyqtSignal()

    def __init__(self, parent=None, capture_mode='click'):
        super().__init__(parent)
        self.capture_mode = capture_mode  # 'click' or 'swipe'
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowModality(Qt.ApplicationModal)  # Prevents other dialogs from stealing clicks
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)
        
        # Cover all screens
        screen_geometry = QApplication.desktop().geometry()
        self.setGeometry(screen_geometry)
        
        # State
        self.start_pos = None
        self.current_pos = None
        
        # Force focus
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self.setFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80)) # Light dim
        
        # Draw instructions
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        
        text = "Click anywhere to capture coordinates (ESC to cancel)"
        if self.capture_mode == 'swipe':
            text = "Click and drag to capture swipe path (ESC to cancel)"
            
        painter.drawText(self.rect(), Qt.AlignCenter, text)

        # Draw swipe line if dragging
        if self.capture_mode == 'swipe' and self.start_pos and self.current_pos:
            pen = QPen(QColor(0, 255, 0), 3)
            painter.setPen(pen)
            painter.drawLine(self.start_pos, self.current_pos)
            
            # Draw endpoints
            painter.setBrush(QColor(0, 255, 0))
            painter.drawEllipse(self.start_pos, 4, 4)
            painter.setBrush(QColor(255, 0, 0))
            painter.drawEllipse(self.current_pos, 4, 4)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.globalPos()
            self.current_pos = self.start_pos
            if self.capture_mode == 'click':
                self.captured_click.emit(self.start_pos.x(), self.start_pos.y())
                self.close()
            else:
                self.update()

    def mouseMoveEvent(self, event):
        if self.capture_mode == 'swipe' and self.start_pos:
            self.current_pos = event.globalPos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.capture_mode == 'swipe':
            end_pos = event.globalPos()
            # If distance is too small, ignore it
            dist = (end_pos.x() - self.start_pos.x())**2 + (end_pos.y() - self.start_pos.y())**2
            if dist > 25: # At least 5px movement
                self.captured_swipe.emit(
                    self.start_pos.x(), self.start_pos.y(),
                    end_pos.x(), end_pos.y()
                )
            self.close()

class ImageActionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Image Action")
        self.setMinimumWidth(400)
        self.image_path = ""
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Image selection
        row_img = QHBoxLayout()
        self.lbl_path = QLabel("No image selected")
        btn_browse = QPushButton("Browse Image...")
        btn_browse.clicked.connect(self.browse)
        row_img.addWidget(self.lbl_path)
        row_img.addWidget(btn_browse)
        layout.addLayout(row_img)

        # Action Type
        self.rad_wait = QRadioButton("Wait for image to appear")
        self.rad_click = QRadioButton("Wait for image, then Click its center")
        self.rad_click.setChecked(True)
        self.rad_if_det = QRadioButton("IF image detected (starts a block)")
        self.rad_if_not = QRadioButton("IF image NOT detected (starts a block)")
        self.rad_disappear = QRadioButton("Wait for image to DISAPPEAR")

        layout.addWidget(self.rad_wait)
        layout.addWidget(self.rad_click)
        layout.addWidget(self.rad_if_det)
        layout.addWidget(self.rad_if_not)
        layout.addWidget(self.rad_disappear)

        # Timeout
        row_time = QHBoxLayout()
        row_time.addWidget(QLabel("Timeout (max wait seconds):"))
        self.spin_timeout = QDoubleSpinBox()
        self.spin_timeout.setRange(1.0, 3600.0)
        self.spin_timeout.setValue(30.0)
        row_time.addWidget(self.spin_timeout)
        layout.addLayout(row_time)

        # Post-action delay
        row_delay = QHBoxLayout()
        row_delay.addWidget(QLabel("Delay after action (seconds):"))
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.0, 60.0)
        self.spin_delay.setValue(0.5)
        row_delay.addWidget(self.spin_delay)
        layout.addLayout(row_delay)

        # Buttons
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Add Step")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.image_path = path
            import os
            self.lbl_path.setText(os.path.basename(path))

    def get_data(self):
        t = 'click_image'
        if self.rad_wait.isChecked(): t = 'wait_image'
        elif self.rad_if_det.isChecked(): t = 'if_detected'
        elif self.rad_if_not.isChecked(): t = 'if_not_detected'
        elif self.rad_disappear.isChecked(): t = 'wait_disappear'

        return {
            'type': t,
            'image_path': self.image_path,
            'timeout': self.spin_timeout.value(),
            'delay': self.spin_delay.value()
        }

class MacroBuilderDialog(QDialog):
    def __init__(self, pair_name, parent=None, initial_steps=None):
        super().__init__(parent)
        self.pair_name = pair_name
        import copy
        self.steps = copy.deepcopy(initial_steps) if initial_steps else []
        self.setWindowTitle(f"Macro Builder — {self.pair_name}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.setModal(True)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Info
        info = QLabel(
            "<b>Build a custom sequence of actions to automate this pair.</b><br>"
            "If macro steps are defined here, they will completely replace "
            "the default Coinglass automation flow for this pair.<br>"
            "<i>Note: Use {pair} in text fields to insert the pair name automatically.</i>"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#bbb;font-size:11px;background:#1e1e2e;padding:8px;border-radius:4px;")
        layout.addWidget(info)
        
        # Actions Toolbar
        tb_layout = QHBoxLayout()
        btn_click = QPushButton("+ Click")
        btn_swipe = QPushButton("+ Swipe")
        btn_type  = QPushButton("+ Type Text")
        btn_img   = QPushButton("+ Image Action")
        btn_wait  = QPushButton("+ Wait")
        btn_find  = QPushButton("+ Find Coinglass")
        btn_center = QPushButton("+ Center Chart")
        btn_learn_liq = QPushButton("+ Learn Liquidity Data")
        btn_adv_center = QPushButton("+ Advanced Center Chart")
        btn_chatgpt = QPushButton("+ chatpt model for reading 111")
        btn_deepseek = QPushButton("+ deepseek reader 11")
        btn_gpt2nd = QPushButton("+ gpt 2nd")
        btn_deepseek_2nd = QPushButton("+ deepseek 2nd")
        btn_endif = QPushButton("+ End If")
        
        for btn in [btn_click, btn_swipe, btn_type, btn_img, btn_wait, btn_find, btn_center, btn_learn_liq, btn_adv_center, btn_chatgpt, btn_deepseek, btn_gpt2nd, btn_deepseek_2nd, btn_endif]:
            btn.setStyleSheet(
                "QPushButton{background:#2a2a4a;color:#aaccff;border:1px solid #446;border-radius:3px;padding:4px;}"
                "QPushButton:hover{background:#3a3a6a;}"
            )
            tb_layout.addWidget(btn)
        
        layout.addLayout(tb_layout)
        
        btn_click.clicked.connect(self.add_click)
        btn_swipe.clicked.connect(self.add_swipe)
        btn_type.clicked.connect(self.add_type)
        btn_img.clicked.connect(self.add_image_action)
        btn_wait.clicked.connect(self.add_wait)
        btn_find.clicked.connect(self.add_find_coinglass)
        btn_center.clicked.connect(self.add_center_chart)
        btn_learn_liq.clicked.connect(self.add_learn_liquidity)
        btn_adv_center.clicked.connect(self.add_advanced_center_chart)
        btn_chatgpt.clicked.connect(self.add_chatgpt_model)
        btn_deepseek.clicked.connect(self.add_deepseek_reader)
        btn_gpt2nd.clicked.connect(self.add_gpt_2nd)
        btn_deepseek_2nd.clicked.connect(self.add_deepseek_2nd)
        btn_endif.clicked.connect(self.add_end_if)
        
        # List widget
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.itemDoubleClicked.connect(self.edit_step)
        
        # Override dropEvent to automatically refresh numbering
        original_drop = self.list_widget.dropEvent
        def on_drop(event):
            original_drop(event)
            self.steps = self.get_ordered_steps()
            self.refresh_list()
        self.list_widget.dropEvent = on_drop
        
        self.list_widget.setStyleSheet(
            "QListWidget { background: #1e1e1e; color: #eee; border: 1px solid #555; } "
            "QListWidget::item { padding: 4px; border-bottom: 1px solid #333; } "
            "QListWidget::item:selected { background: #2a4a2a; }"
        )
        layout.addWidget(self.list_widget)
        self.refresh_list()
        
        # Item Toolbar
        itb_layout = QHBoxLayout()
        btn_rm = QPushButton("Remove Selected")
        btn_clear = QPushButton("Clear All")
        
        btn_rm.setStyleSheet("QPushButton{color:#ff8888;}")
        btn_clear.setStyleSheet("QPushButton{color:#ff8888;}")
        
        btn_rm.clicked.connect(self.remove_selected)
        btn_clear.clicked.connect(self.clear_all)
        
        itb_layout.addWidget(btn_rm)
        itb_layout.addStretch()
        itb_layout.addWidget(btn_clear)
        layout.addLayout(itb_layout)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save Macro")
        btn_cancel = QPushButton("Cancel")
        
        btn_save.setStyleSheet(
            "QPushButton{background:#1a6b2a;color:white;border-radius:3px;padding:6px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#22882e;}"
        )
        btn_cancel.setStyleSheet(
            "QPushButton{background:#3a3a3a;color:#ccc;border-radius:3px;padding:6px 14px;}"
            "QPushButton:hover{background:#505050;}"
        )
        
        def on_save():
            ordered = self.get_ordered_steps()
            if ordered:
                self.steps = ordered
            self.accept()
            
        btn_save.clicked.connect(on_save)
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

    def refresh_list(self):
        self.list_widget.clear()
        indent_level = 0
        
        for i, step in enumerate(self.steps):
            t = step.get('type')
            
            # Decrease indent before rendering End If
            if t == 'end_if' and indent_level > 0:
                indent_level -= 1
                
            prefix = "    " * indent_level
            text = f"{prefix}[{i+1}] "
            
            if t == 'click':
                text += f"👆 Click at ({step.get('x')}, {step.get('y')})"
            elif t == 'swipe':
                text += f"👉 Swipe from ({step.get('start_x')}, {step.get('start_y')}) to ({step.get('end_x')}, {step.get('end_y')})"
            elif t == 'type':
                text += f"⌨️ Type text: '{step.get('text')}'"
            elif t == 'wait':
                text += f"⏳ Wait {step.get('delay')} seconds"
            elif t == 'find_coinglass':
                text += f"🔎 Auto-Find & Focus Coinglass"
            elif t == 'center_chart':
                text += f"🎯 Center Chart ({step.get('upper_blocks', 5)} upper, {step.get('lower_blocks', 5)} lower)"
            elif t == 'learn_liquidity':
                text += f"🧠 Learn Liquidity Data ({step.get('upper_blocks', 5)} upper, {step.get('lower_blocks', 5)} lower)"
            elif t == 'advanced_center_chart':
                text += f"🔭 Advanced Center Chart (auto-detect + zoom analysis)"
            elif t == 'chatgpt_model':
                text += f"🤖 chatpt model for reading 111"
            elif t == 'deepseek_reader':
                text += f"📊 deepseek reader 11"
            elif t == 'gpt_2nd':
                text += f"🧠 gpt 2nd"
            elif t == 'deepseek_2nd':
                text += f"🔍 deepseek 2nd"
            elif t == 'wait_image':
                import os
                name = os.path.basename(step.get('image_path', 'unknown'))
                text += f"🖼️ Wait for image ({name}) max {step.get('timeout')}s"
            elif t == 'click_image':
                import os
                name = os.path.basename(step.get('image_path', 'unknown'))
                text += f"🖼️ Click image ({name}) max wait {step.get('timeout')}s"
            elif t == 'if_detected':
                import os
                name = os.path.basename(step.get('image_path', 'unknown'))
                text += f"🟩 IF Image Detected ({name}) max wait {step.get('timeout')}s:"
                indent_level += 1
            elif t == 'if_not_detected':
                import os
                name = os.path.basename(step.get('image_path', 'unknown'))
                text += f"🟥 IF Image NOT Detected ({name}) max wait {step.get('timeout')}s:"
                indent_level += 1
            elif t == 'wait_disappear':
                import os
                name = os.path.basename(step.get('image_path', 'unknown'))
                text += f"🫥 Wait for image to DISAPPEAR ({name}) max wait {step.get('timeout')}s"
            elif t == 'end_if':
                text += f"🛑 END IF"
            
            if step.get('delay', 0) > 0 and t not in ('wait', 'find_coinglass', 'if_detected', 'if_not_detected', 'end_if'):
                text += f" (then wait {step.get('delay')}s)"
                
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, step)
            self.list_widget.addItem(item)

    # Reorder hook
    def get_ordered_steps(self):
        ordered = []
        for i in range(self.list_widget.count()):
            data = self.list_widget.item(i).data(Qt.UserRole)
            if data is not None:
                ordered.append(data)
        return ordered

    # --- Actions ---
    def remove_selected(self):
        selected = self.list_widget.selectedItems()
        if not selected: return
        
        # Remove from bottom to top to avoid index shifting issues
        for item in reversed(selected): # Iterate in reverse to avoid index issues
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
            
        self.steps = self.get_ordered_steps()
        self.refresh_list()

    def clear_all(self):
        if QMessageBox.question(self, "Clear All", "Delete all macro steps?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.steps = []
            self.refresh_list()

    def edit_step(self, item):
        step = item.data(Qt.UserRole)
        import json
        current_json = json.dumps(step, indent=4)
        text, ok = QInputDialog.getMultiLineText(
            self, "Edit Step", 
            "Modify step properties directly (JSON format):", 
            current_json
        )
        if ok:
            try:
                new_step = json.loads(text)
                item.setData(Qt.UserRole, new_step)
                # Need to update self.steps so refresh_list() renders it properly
                self.steps = self.get_ordered_steps()
                self.refresh_list()
            except Exception as e:
                QMessageBox.warning(self, "Invalid JSON", f"Failed to parse properties:\n{e}")

    def add_step(self, step):
        self.steps = self.get_ordered_steps()
        self.steps.append(step)
        self.refresh_list()

    def add_click(self):
        # Use showMinimized instead of hide — hiding a modal QDialog causes
        # exec_() to immediately return Rejected, breaking the save flow.
        self.showMinimized()
        main_win = self.parent()
        if main_win: main_win.showMinimized()
            
        self.overlay = ScreenOverlay(self, capture_mode='click')
        def on_captured(x, y):
            def prompt():
                if main_win: main_win.showNormal()
                self.show()
                self.raise_()
                self.activateWindow()
                delay, ok = QInputDialog.getDouble(self, "Post-Click Delay", "Seconds to wait after click:", 0.5, 0, 60, 2)
                if ok:
                    self.add_step({'type': 'click', 'x': x, 'y': y, 'delay': delay})
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, prompt)
            
        def on_cancelled():
            if main_win: main_win.showNormal()
            self.show()
            self.raise_()
            self.activateWindow()
            
        self.overlay.captured_click.connect(on_captured)
        self.overlay.cancelled.connect(on_cancelled)
        self.overlay.show()

    def add_swipe(self):
        self.showMinimized()
        main_win = self.parent()
        if main_win: main_win.showMinimized()
            
        self.overlay = ScreenOverlay(self, capture_mode='swipe')
        def on_captured(sx, sy, ex, ey):
            def prompt():
                if main_win: main_win.showNormal()
                self.show()
                self.raise_()
                self.activateWindow()
                delay, ok = QInputDialog.getDouble(self, "Post-Swipe Delay", "Seconds to wait after swipe:", 0.5, 0, 60, 2)
                if ok:
                    self.add_step({'type': 'swipe', 'start_x': sx, 'start_y': sy, 'end_x': ex, 'end_y': ey, 'delay': delay})
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, prompt)
            
        def on_cancelled():
            if main_win: main_win.showNormal()
            self.show()
            self.raise_()
            self.activateWindow()
            
        self.overlay.captured_swipe.connect(on_captured)
        self.overlay.cancelled.connect(on_cancelled)
        self.overlay.show()

    def add_type(self):
        text, ok = QInputDialog.getText(self, "Type Text", "Text to type (use {pair} for dynamic variable):", text="{pair}")
        if ok and text:
            delay, ok2 = QInputDialog.getDouble(self, "Post-Type Delay", "Seconds to wait after typing:", 1.0, 0, 60, 2)
            if ok2:
                self.add_step({'type': 'type', 'text': text, 'delay': delay})

    def add_wait(self):
        delay, ok = QInputDialog.getDouble(self, "Add Wait", "Seconds to wait:", 1.0, 0, 3600, 2)
        if ok:
            self.add_step({'type': 'wait', 'delay': delay})

    def add_image_action(self):
        diag = ImageActionDialog(self)
        if diag.exec_() and diag.image_path:
            self.add_step(diag.get_data())

    def add_find_coinglass(self):
        self.add_step({'type': 'find_coinglass', 'delay': 1.0})

    def add_center_chart(self):
        upper, ok1 = QInputDialog.getInt(self, "Upper Blocks Visible", "How many blocks ABOVE current price should be visible?", 5, 1, 50)
        if ok1:
            lower, ok2 = QInputDialog.getInt(self, "Lower Blocks Visible", "How many blocks BELOW current price should be visible?", 5, 1, 50)
            if ok2:
                self.add_step({
                    'type': 'center_chart',
                    'upper_blocks': upper,
                    'lower_blocks': lower,
                    'delay': 1.0
                })

    def add_learn_liquidity(self):
        upper, ok1 = QInputDialog.getInt(self, "Upper Blocks", "How many blocks to read from current to UPPER?", 5, 1, 50)
        if ok1:
            lower, ok2 = QInputDialog.getInt(self, "Lower Blocks", "How many blocks to read from current to LOWER?", 5, 1, 50)
            if ok2:
                self.add_step({
                    'type': 'learn_liquidity',
                    'upper_blocks': upper,
                    'lower_blocks': lower,
                    'delay': 1.0
                })

    def add_advanced_center_chart(self):
        self.add_step({'type': 'advanced_center_chart', 'delay': 1.0})

    def add_chatgpt_model(self):
        self.add_step({'type': 'chatgpt_model', 'delay': 1.0})

    def add_deepseek_reader(self):
        self.add_step({'type': 'deepseek_reader', 'delay': 1.0})

    def add_gpt_2nd(self):
        self.add_step({'type': 'gpt_2nd', 'delay': 1.0})

    def add_deepseek_2nd(self):
        self.add_step({'type': 'deepseek_2nd', 'delay': 1.0})

    def add_end_if(self):
        self.add_step({'type': 'end_if'})

class GlobalMacroManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Global Macro Library")
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)
        self.macros = load_global_macros()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        info = QLabel(
            "<b>Macro Library</b><br>"
            "Create reusable automation sequences here. You can assign these macros to specific "
            "trading pairs in their individual settings menus."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#bbb;font-size:11px;background:#1e1e2e;padding:8px;border-radius:4px;")
        layout.addWidget(info)
        
        # List widget
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget { background: #1e1e1e; color: #eee; border: 1px solid #555; } "
            "QListWidget::item { padding: 6px; border-bottom: 1px solid #333; } "
            "QListWidget::item:selected { background: #2a4a2a; }"
        )
        self.list_widget.itemDoubleClicked.connect(self.edit_macro)
        layout.addWidget(self.list_widget)
        self.refresh_list()
        
        # Tools
        tb = QHBoxLayout()
        btn_new = QPushButton("+ New Macro")
        btn_edit = QPushButton("✏️ Edit Selected")
        btn_clone = QPushButton("📋 Clone")
        btn_rename = QPushButton("✏️ Rename")
        btn_del = QPushButton("🗑 Delete")
        
        for btn in [btn_new, btn_edit, btn_clone, btn_rename, btn_del]:
            btn.setStyleSheet(
                "QPushButton{background:#2a2a4a;color:#aaccff;border:1px solid #446;border-radius:3px;padding:5px;}"
                "QPushButton:hover{background:#3a3a6a;}"
            )
            tb.addWidget(btn)
        btn_del.setStyleSheet(btn_del.styleSheet().replace("color:#aaccff", "color:#ff8888"))
        
        layout.addLayout(tb)
        
        btn_new.clicked.connect(self.new_macro)
        btn_edit.clicked.connect(lambda: self.edit_macro(self.list_widget.currentItem()))
        btn_clone.clicked.connect(self.clone_macro)
        btn_rename.clicked.connect(self.rename_macro)
        btn_del.clicked.connect(self.delete_macro)
        
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(
            "QPushButton{background:#3a3a3a;color:#ccc;border-radius:3px;padding:6px 14px;}"
            "QPushButton:hover{background:#505050;}"
        )
        btn_close.clicked.connect(self.accept)
        
        bh = QHBoxLayout()
        bh.addStretch()
        bh.addWidget(btn_close)
        layout.addLayout(bh)

    def refresh_list(self):
        self.list_widget.clear()
        for name, steps in sorted(self.macros.items()):
            item = QListWidgetItem(f"📜 {name}   ({len(steps)} steps)")
            item.setData(Qt.UserRole, name)
            self.list_widget.addItem(item)
            
    def new_macro(self):
        name, ok = QInputDialog.getText(self, "New Macro", "Enter a unique name for this macro:")
        if ok and name:
            name = name.strip()
            if not name: return
            if name in self.macros:
                QMessageBox.warning(self, "Error", "A macro with this name already exists!")
                return
            
            # Open builder with empty steps — only save if user clicks Save
            dialog = MacroBuilderDialog(name, self, [])
            if dialog.exec_():
                self.macros[name] = dialog.steps
                save_global_macros(self.macros)
                self.refresh_list()

    def edit_macro(self, item=None):
        if not item: return
        name = item.data(Qt.UserRole)
        steps = self.macros.get(name, [])
        dialog = MacroBuilderDialog(name, self, steps)
        if dialog.exec_():
            self.macros[name] = dialog.steps
            save_global_macros(self.macros)
            self.refresh_list()

    def delete_macro(self):
        item = self.list_widget.currentItem()
        if not item: return
        name = item.data(Qt.UserRole)
        if QMessageBox.question(self, "Delete Macro", f"Are you sure you want to delete '{name}'?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            del self.macros[name]
            save_global_macros(self.macros)
            self.refresh_list()

    def clone_macro(self):
        item = self.list_widget.currentItem()
        if not item: return
        src_name = item.data(Qt.UserRole)
        new_name, ok = QInputDialog.getText(self, "Clone Macro", f"Enter name for the copy of '{src_name}':")
        if ok and new_name:
            new_name = new_name.strip()
            if not new_name: return
            if new_name in self.macros:
                QMessageBox.warning(self, "Error", "A macro with this name already exists!")
                return
            import copy
            self.macros[new_name] = copy.deepcopy(self.macros[src_name])
            save_global_macros(self.macros)
            self.refresh_list()

    def rename_macro(self):
        item = self.list_widget.currentItem()
        if not item: return
        old_name = item.data(Qt.UserRole)
        new_name, ok = QInputDialog.getText(self, "Rename Macro", f"Enter new name for '{old_name}':", text=old_name)
        if ok and new_name:
            new_name = new_name.strip()
            if not new_name or new_name == old_name: return
            if new_name in self.macros:
                QMessageBox.warning(self, "Error", "A macro with this name already exists!")
                return
            self.macros[new_name] = self.macros.pop(old_name)
            save_global_macros(self.macros)
            self.refresh_list()
