import sys
import json
import os
import winreg
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QComboBox, QLabel, QLineEdit, 
                             QPushButton, QScrollArea, QFrame, QSystemTrayIcon,
                             QMenu, QAction, QMessageBox, QInputDialog,
                             QTabWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, 
                             QCheckBox, QDoubleSpinBox, QDialog, QListWidget, QListWidgetItem)
from PyQt5.QtGui import QIcon, QPixmap, QFont
from PyQt5.QtCore import Qt, pyqtSignal, QObject

import psutil
import win32gui
import win32process
import subprocess

from controller_mapper import ControllerThread
from hud_widget import RadialMenuWidget, DEFAULT_HUD_ITEMS, SLOT_DIRECTIONS

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
CONTROLLER_IMG = r"xbox_controller_base_1774408660399.png"

DARK_THEME_QSS = """
QMainWindow, QWidget {
    background-color: #0e0e0e;
    color: #ffffff;
    font-family: 'Segoe UI', 'Manrope', 'Space Grotesk', Arial, sans-serif;
    font-size: 13px;
}

QPushButton {
    background-color: #262626;
    color: #ffffff;
    border: 1px solid #333333;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
    text-transform: uppercase;
}

QPushButton:hover {
    background-color: #43b7ff;
    color: #00324c;
    border: 1px solid #43b7ff;
}

QPushButton:pressed {
    background-color: #0fa7f2;
}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    border-radius: 6px;
    padding: 6px 8px;
    color: #ffffff;
}

QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #43b7ff;
}

QTabWidget::pane {
    border: 1px solid #262626;
    border-radius: 8px;
    background: #1a1a1a;
}

QTabBar::tab {
    background: #1a1a1a;
    color: #adaaaa;
    padding: 10px 20px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background: #0e0e0e;
    color: #43b7ff;
    border-bottom: 2px solid #43b7ff;
}

QTabBar::tab:hover {
    background: #262626;
    color: #ffffff;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

/* ScrollBar Styling */
QScrollBar:vertical {
    border: none;
    background: #0e0e0e;
    width: 6px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #262626;
    min-height: 20px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: #43b7ff;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class OutputRedirector(QObject):
    text_written = pyqtSignal(str)

    def write(self, text):
        self.text_written.emit(str(text))

    def flush(self):
        pass

class ProcessSelectorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Application to Bind")
        self.resize(500, 600)
        self.setStyleSheet(DARK_THEME_QSS)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel("Select a running application to auto-switch to this profile:")
        info_label.setStyleSheet("color: #adaaaa; font-weight: bold;")
        layout.addWidget(info_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search running applications...")
        self.search_input.textChanged.connect(self.filter_processes)
        layout.addWidget(self.search_input)
        
        self.process_list = QListWidget()
        self.process_list.setStyleSheet("QListWidget { background-color: #1a1a1a; border: 1px solid #333333; border-radius: 8px; padding: 5px; } QListWidget::item { padding: 8px; border-bottom: 1px solid #262626; } QListWidget::item:selected { background-color: #43b7ff; color: #00324c; border-radius: 4px; }")
        layout.addWidget(self.process_list)
        
        btn_layout = QHBoxLayout()
        select_btn = QPushButton("🔗 Bind Selected")
        select_btn.setStyleSheet("background-color: #238636;")
        select_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(select_btn)
        layout.addLayout(btn_layout)
        
        self.selected_process = None
        self.all_items = []
        self.populate_processes()

    def populate_processes(self):
        windows = []
        def enum_windows_callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc = psutil.Process(pid)
                    if proc.name().lower() not in ["explorer.exe", "shellexperiencehost.exe", "searchapp.exe"]:
                        windows.append((win32gui.GetWindowText(hwnd), proc.name()))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        
        win32gui.EnumWindows(enum_windows_callback, None)
        
        # Deduplicate by process name
        seen_procs = set()
        unique_windows = []
        for title, proc_name in windows:
            if proc_name not in seen_procs:
                seen_procs.add(proc_name)
                unique_windows.append((title, proc_name))
                
        unique_windows.sort(key=lambda x: x[0].lower())
        
        for title, proc_name in unique_windows:
            item = QListWidgetItem(f"{title}\n[{proc_name}]")
            item.setData(Qt.UserRole, proc_name)
            self.process_list.addItem(item)
            self.all_items.append(item)

    def filter_processes(self, text):
        text = text.lower()
        for i in range(self.process_list.count()):
            item = self.process_list.item(i)
            item.setHidden(text not in item.text().lower())

    def accept(self):
        current = self.process_list.currentItem()
        if current:
            self.selected_process = current.data(Qt.UserRole)
        super().accept()

class VisualizerWidget(QWidget):
    button_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(500, 500)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.bg_label = QLabel(self)
        try:
            pixmap = QPixmap(CONTROLLER_IMG)
            # Scale down image to fit
            pixmap = pixmap.scaled(500, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.bg_label.setPixmap(pixmap)
        except Exception:
            self.bg_label.setText("Controller Image Not Found")
            
        self.bg_label.setGeometry(0, 0, 500, 500)

        # Map typical coordinates (X, Y, W, H) on a 500x500 image. 
        self.btn_rects = {
            "LT": (125, 75, 50, 30),
            "RT": (325, 75, 50, 30),
            "LB": (120, 115, 60, 25),
            "RB": (320, 115, 60, 25),
            "Y": (350, 150, 30, 30),
            "B": (380, 180, 30, 30),
            "A": (350, 210, 30, 30),
            "X": (320, 180, 30, 30),
            "LS": (110, 170, 50, 50),
            "RS": (285, 240, 50, 50),
            "Up": (183, 240, 20, 20),
            "Down": (183, 280, 20, 20),
            "Left": (163, 260, 20, 20),
            "Right": (203, 260, 20, 20),
            "Back": (205, 185, 25, 25),
            "Start": (270, 185, 25, 25),
            "Guide": (230, 140, 40, 35),
        }

        self.overlay_btns = {}
        for b_name, (x, y, w, h) in self.btn_rects.items():
            btn = QPushButton(self)
            btn.setGeometry(x, y, w, h)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 60);
                    border: 1px solid rgba(255, 255, 255, 100);
                    border-radius: 15px;
                }
                QPushButton:hover {
                    background-color: rgba(52, 152, 219, 100);
                    border: 2px solid #3498db;
                }
            """)
            btn.setToolTip(b_name)
            # Capture the btn name correctly in the lambda
            btn.clicked.connect(lambda checked, n=b_name: self.button_clicked.emit(n))
            self.overlay_btns[b_name] = btn

class ConfigUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xbox Controller Mapper Config")
        self.resize(1000, 700)
        self.config_data = {"profiles": {}}
        self.current_profile = None
        self.current_hud_name = "Default HUD"
        
        # Setup output redirection for logs
        self.redirector = OutputRedirector()
        self.redirector.text_written.connect(self.append_log)
        sys.stdout = self.redirector
        sys.stderr = self.redirector
        
        # HUD menu will be initialized with items from config after load_config
        self.hud_menu = RadialMenuWidget()
        
        self.init_ui()
        self.load_config()
        self.init_tray()
        
        # Start background controller thread
        self.controller_thread = ControllerThread()
        self.controller_thread.profile_changed.connect(self.show_profile_toast)
        self.controller_thread.controllers_changed.connect(self.on_controllers_changed)
        self.controller_thread.show_hud_signal.connect(self.show_hud_with_items)
        self.controller_thread.hide_hud_signal.connect(self.hud_menu.hide_hud)
        self.controller_thread.update_hud_signal.connect(self.hud_menu.update_selection)
        self.controller_thread.start()

    def show_hud_with_items(self, items):
        self.hud_menu.set_items(items)
        self.hud_menu.show_hud()

    def on_controllers_changed(self, controllers, active_id):
        self.controller_combo.blockSignals(True)
        self.controller_combo.clear()
        
        if not controllers:
            self.controller_combo.addItem("No Controller Detected", -1)
        else:
            for i, c in enumerate(controllers):
                self.controller_combo.addItem(f"{c['name']} (ID: {c['id']})", c['id'])
                if c['id'] == active_id:
                    self.controller_combo.setCurrentIndex(i)
                    
        self.controller_combo.blockSignals(False)

    def on_controller_selected(self, index):
        if index >= 0 and self.controller_combo.itemData(index) != -1:
            instance_id = self.controller_combo.itemData(index)
            self.controller_thread.set_active_controller(instance_id)

    def show_profile_toast(self, profile_name):
        self.tray_icon.showMessage(
            "Profile Changed",
            f"Active Profile: {profile_name}",
            QSystemTrayIcon.Information,
            1500
        )

    def init_ui(self):
        self.setStyleSheet(DARK_THEME_QSS)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget) 
        
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        
        # --- TAB 1: Configuration ---
        config_tab = QWidget()
        config_layout = QHBoxLayout(config_tab)

        # Left Column: Visualizer
        left_layout = QVBoxLayout()
        self.visualizer = VisualizerWidget()
        self.visualizer.button_clicked.connect(self.on_visualizer_clicked)
        left_layout.addWidget(self.visualizer, alignment=Qt.AlignCenter)
        config_layout.addLayout(left_layout, 1)

        # Right Column: Config UI
        right_layout = QVBoxLayout()
        
        # Controller Selection Area
        controller_layout = QHBoxLayout()
        controller_label = QLabel("Active Controller:")
        controller_label.setStyleSheet("font-weight: bold;")
        self.controller_combo = NoScrollComboBox()
        self.controller_combo.setMinimumWidth(250)
        self.controller_combo.currentIndexChanged.connect(self.on_controller_selected)
        
        self.haptic_checkbox = QCheckBox("Enable Rumble")
        self.haptic_checkbox.setStyleSheet("font-weight: bold;")
        self.haptic_checkbox.stateChanged.connect(self.save_config)
        
        controller_layout.addWidget(controller_label)
        controller_layout.addWidget(self.controller_combo)
        controller_layout.addWidget(self.haptic_checkbox)
        controller_layout.addStretch()
        
        right_layout.addLayout(controller_layout)

        # Mouse / Scroll Settings Row
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("Mouse Speed:"))
        self.mouse_spin = QDoubleSpinBox()
        self.mouse_spin.setRange(1.0, 50.0)
        self.mouse_spin.setValue(self.config_data.get("mouse_speed", 15.0))
        self.mouse_spin.valueChanged.connect(self.save_config)
        settings_layout.addWidget(self.mouse_spin)
        
        settings_layout.addSpacing(20)
        
        settings_layout.addWidget(QLabel("Scroll Speed:"))
        self.scroll_spin = QDoubleSpinBox()
        self.scroll_spin.setRange(0.01, 2.0)
        self.scroll_spin.setSingleStep(0.05)
        self.scroll_spin.setValue(self.config_data.get("scroll_speed", 0.2))
        self.scroll_spin.valueChanged.connect(self.save_config)
        settings_layout.addWidget(self.scroll_spin)
        
        settings_layout.addStretch()
        right_layout.addLayout(settings_layout)

        # Profile Selection Area
        profile_container = QVBoxLayout()
        
        profile_layout = QHBoxLayout()
        profile_label = QLabel("Profile:")
        profile_label.setStyleSheet("font-weight: bold;")
        self.profile_combo = NoScrollComboBox()
        self.profile_combo.currentTextChanged.connect(self.on_profile_changed)
        
        add_profile_btn = QPushButton("+ New")
        add_profile_btn.clicked.connect(self.add_profile)
        
        delete_profile_btn = QPushButton("Delete")
        delete_profile_btn.setStyleSheet("background-color: #A31515;")
        delete_profile_btn.clicked.connect(self.delete_profile)

        profile_layout.addWidget(profile_label)
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addWidget(add_profile_btn)
        profile_layout.addWidget(delete_profile_btn)
        
        bind_layout = QHBoxLayout()
        self.bound_app_label = QLabel("Bound App: None")
        self.bound_app_label.setStyleSheet("font-style: italic; color: #adaaaa; font-weight: bold;")
        
        self.bind_app_btn = QPushButton("🔗 Bind to App")
        self.bind_app_btn.clicked.connect(self.bind_app_to_profile)
        
        bind_layout.addWidget(self.bound_app_label, 1)
        bind_layout.addWidget(self.bind_app_btn)
        
        profile_container.addLayout(profile_layout)
        profile_container.addLayout(bind_layout)
        
        right_layout.addLayout(profile_container)

        # Scroll Area for Mappings
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.mapping_widget = QWidget()
        self.mapping_widget.setStyleSheet("background-color: transparent;")
        self.mapping_layout = QVBoxLayout(self.mapping_widget)
        self.mapping_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.mapping_widget)
        
        right_layout.addWidget(self.scroll_area)

        # Bottom Buttons
        bottom_layout = QHBoxLayout()
        add_mapping_btn = QPushButton("Add Custom Row")
        add_mapping_btn.clicked.connect(self.add_mapping)
        save_btn = QPushButton("Save Config")
        save_btn.setStyleSheet("background-color: #238636;") # Greenish save button
        save_btn.clicked.connect(self.save_config)
        
        bottom_layout.addWidget(add_mapping_btn)
        bottom_layout.addWidget(save_btn)
        right_layout.addLayout(bottom_layout)
        
        config_layout.addLayout(right_layout, 1)
        
        self.tabs.addTab(config_tab, "🎮 CONFIGURATION")
        
        # --- TAB 2: Action Library ---
        library_tab = QWidget()
        library_layout = QVBoxLayout(library_tab)
        
        lib_desc = QLabel("1. Select a preset action from the library below:")
        lib_desc.setStyleSheet("font-weight: bold;")
        library_layout.addWidget(lib_desc)
        
        self.preset_tree = QTreeWidget()
        self.preset_tree.setHeaderHidden(True)
        self.preset_tree.setStyleSheet("background-color: #252526; color: #D4D4D4; border: 1px solid #333;")
        
        PRESETS = {
            "📸 Lightroom Classic": [
                ("Undo", "macro", "ctrl+z"),
                ("Redo", "macro", "ctrl+shift+z"),
                ("Copy Settings", "macro", "ctrl+shift+c"),
                ("Paste Settings", "macro", "ctrl+shift+v"),
                ("Export", "macro", "ctrl+shift+e"),
                ("Pick Photo", "key_press", "p"),
                ("Reject Photo", "key_press", "x"),
                ("Compare View", "key_press", "c"),
                ("Grid View", "key_press", "g"),
                ("Develop Module", "key_press", "d")
            ],
            "🌐 Windows / Browser": [
                ("Copy", "macro", "ctrl+c"),
                ("Paste", "macro", "ctrl+v"),
                ("Next Tab", "macro", "ctrl+tab"),
                ("Prev Tab", "macro", "ctrl+shift+tab"),
                ("Close Tab", "macro", "ctrl+w"),
                ("Show Desktop", "macro", "cmd+d")
            ],
            "🎵 Media & System": [
                ("Radial HUD Menu", "radial_menu", ""),
                ("Volume Up", "key_press", "volume_up"),
                ("Volume Down", "key_press", "volume_down"),
                ("Mute", "key_press", "volume_mute"),
                ("Play / Pause", "key_press", "play_pause"),
                ("Next Track", "key_press", "next_track"),
                ("Prev Track", "key_press", "prev_track"),
                ("Open Calculator", "run_app", "calc.exe"),
                ("Open Notepad", "run_app", "notepad.exe")
            ],
            "🖱️ Mouse & Scroll": [
                ("Left Click", "key_press", "mouse_left"),
                ("Right Click", "key_press", "mouse_right"),
                ("Middle Click", "key_press", "mouse_middle"),
                ("Scroll Vertical", "scroll_vertical", ""),
                ("Scroll Horizontal", "scroll_horizontal", "")
            ]
        }
        
        for category, actions in PRESETS.items():
            cat_item = QTreeWidgetItem(self.preset_tree, [category])
            cat_item.setExpanded(True)
            for name, act_type, act_val in actions:
                item = QTreeWidgetItem(cat_item, [f"{name} ({act_val})" if act_val else name])
                item.setData(0, Qt.UserRole, {"type": act_type, "key": act_val})
                
        library_layout.addWidget(self.preset_tree)
        
        assign_layout = QHBoxLayout()
        assign_layout.addWidget(QLabel("2. Assign to Button:"))
        self.assign_btn_combo = NoScrollComboBox()
        self.assign_btn_combo.addItems(["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "LS", "RS", "Up", "Down", "Left", "Right"])
        assign_layout.addWidget(self.assign_btn_combo)
        
        assign_btn = QPushButton("✅ Assign to Profile")
        assign_btn.setStyleSheet("background-color: #238636;")
        assign_btn.clicked.connect(self.assign_preset)
        assign_layout.addWidget(assign_btn)
        
        library_layout.addLayout(assign_layout)
        self.tabs.addTab(library_tab, "📚 ACTION LIBRARY")
        
        # --- TAB 3: User Guide ---
        guide_tab = QWidget()
        guide_layout = QVBoxLayout(guide_tab)
        
        guide_text = QTextEdit()
        guide_text.setReadOnly(True)
        guide_text.setStyleSheet("background-color: #1E1E1E; border: none;")
        guide_text.setHtml("""
        <h2 style='color: #4DAAFE; font-family: sans-serif; margin-bottom: 5px;'>Xbox Controller Mapper Pro - Ultimate Guide</h2>
        <i style='color: #8A8A9A;'>Bilingual Version: English & Tiếng Việt</i>
        
        <p style='font-size: 14px; line-height: 1.5; margin-top: 15px;'>
        <b style='color: #43b7ff; font-size: 16px;'>1. PROFILE MANAGEMENT & APP BINDING</b><br>
        <span style='color: #ffffff;'><b>[EN]</b> Create unlimited control profiles for different apps. Click <b>[+ New]</b>, then <b>[🔗 Bind to App]</b> to select an executable (e.g. <code>Photoshop.exe</code>). The profile will auto-switch when the app is focused!</span><br>
        <span style='color: #adaaaa;'><b>[VN]</b> Tạo Profile riêng cho từng ứng dụng. Nhấn <b>[+ New]</b>, sau đó chọn <b>[🔗 Bind to App]</b> để gán vào một phần mềm cụ thể (vd: <code>Photoshop.exe</code>). App sẽ tự động đổi Profile khi bạn mở cửa sổ đó!</span>
        </p>
        
        <p style='font-size: 14px; line-height: 1.5;'>
        <b style='color: #43b7ff; font-size: 16px;'>2. BASIC MAPPING & COMBOS</b><br>
        <span style='color: #ffffff;'><b>[EN]</b> Click any controller button on the visualizer to add a row. Use <code>key_press</code> for single keys. For <b>Combos</b> (e.g., Shift+Key), rename the button field to <code>LB+A</code> or <code>RT+B</code>. It triggers only when the modifier is held.</span><br>
        <span style='color: #adaaaa;'><b>[VN]</b> Click vào nút trên hình tay cầm để gán phím. Chọn <code>key_press</code> cho phím đơn. Để tạo <b>Tổ hợp phím</b>, hãy sửa tên nút (vd: <code>A</code> thành <code>LB+A</code>). Hành động chỉ kích hoạt khi bạn giữ nút phụ (LB).</span>
        </p>
        
        <p style='font-size: 14px; line-height: 1.5;'>
        <b style='color: #43b7ff; font-size: 16px;'>3. MACROS (SEQUENCE & HOTKEYS)</b><br>
        <span style='color: #ffffff;'><b>[EN]</b> Use <code>macro</code> type for multi-key actions.<br>
        - <b>Hotkeys</b>: Separate with <code>+</code> (e.g., <code>ctrl+shift+s</code>).<br>
        - <b>Sequences</b>: Separate with <code>,</code> (e.g., <code>h,e,l,l,o</code>).</span><br>
        <span style='color: #adaaaa;'><b>[VN]</b> Chọn <code>macro</code> cho các hành động nhiều phím.<br>
        - <b>Phím tắt</b>: Dùng dấu <code>+</code> (vd: <code>ctrl+shift+s</code>).<br>
        - <b>Chuỗi gõ phím</b>: Dùng dấu <code>,</code> (vd: <code>h,e,l,l,o</code>).</span>
        </p>
        
        <p style='font-size: 14px; line-height: 1.5;'>
        <b style='color: #43b7ff; font-size: 16px;'>4. MOUSE & SCROLL CONTROL</b><br>
        <span style='color: #ffffff;'><b>[EN]</b> Map <code>mouse_x</code>, <code>mouse_y</code>, or <code>scroll</code> actions to Analog Sticks. Click the LS/RS center icons on the visualizer to generate these rows instantly. For clicks, use <code>mouse_left</code> as a key.</span><br>
        <span style='color: #adaaaa;'><b>[VN]</b> Gán <code>mouse_x</code>, <code>mouse_y</code>, hoặc <code>scroll</code> cho cần Analog. Click vào tâm LS/RS trên hình để tạo nhanh các dòng này. Để click chuột, nhập giá trị phím là <code>mouse_left</code>.</span>
        </p>
        
        <p style='font-size: 14px; line-height: 1.5;'>
        <b style='color: #43b7ff; font-size: 16px;'>5. MULTI RADIAL HUD MENUS</b><br>
        <span style='color: #ffffff;'><b>[EN]</b> Select <code>radial_menu</code> and type the HUD name (from 🎯 HUD Settings). This opens a circular overlay with 8 slots. Perfect for media or tool selection.</span><br>
        <span style='color: #adaaaa;'><b>[VN]</b> Chọn <code>radial_menu</code> và nhập tên HUD (trong tab 🎯 HUD Settings). Một menu tròn 8 ô sẽ hiện ra khi nhấn nút. Rất hữu ích cho phím tắt nhanh hoặc Media.</span>
        </p>

        <p style='font-size: 14px; line-height: 1.5;'>
        <b style='color: #43b7ff; font-size: 16px;'>6. DEV TOOLS & RELOAD</b><br>
        <span style='color: #ffffff;'><b>[EN]</b> Right-click the tray icon for <b>Restart App</b> to apply code changes. Check the <b>📝 TERMINAL LOGS</b> tab to debug profile switching in real-time.</span><br>
        <span style='color: #adaaaa;'><b>[VN]</b> Chuột phải vào icon dưới khay hệ thống để chọn <b>Restart App</b>. Xem tab <b>📝 TERMINAL LOGS</b> để theo dõi quá trình đổi Profile và gán nút trực tiếp.</span>
        </p>
        """)
        guide_layout.addWidget(guide_text)
        self.tabs.addTab(guide_tab, "📖 USER GUIDE")

        # --- TAB 4: HUD Settings ---
        self._build_hud_settings_tab()

        # --- TAB 5: Terminal Logs ---
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setStyleSheet("background-color: #000000; color: #4DAAFE; font-family: Consolas, monospace; border: 1px solid #333;")
        logs_layout.addWidget(self.log_text_edit)
        
        clear_logs_btn = QPushButton("🧹 Clear Logs")
        clear_logs_btn.setStyleSheet("background-color: #262626;")
        clear_logs_btn.clicked.connect(self.log_text_edit.clear)
        logs_layout.addWidget(clear_logs_btn, alignment=Qt.AlignRight)
        
        self.tabs.addTab(logs_tab, "📝 TERMINAL LOGS")

        self.mapping_fields = []
        
    def append_log(self, text):
        if hasattr(self, 'log_text_edit'):
            self.log_text_edit.moveCursor(self.log_text_edit.textCursor().End)
            self.log_text_edit.insertPlainText(text)
            self.log_text_edit.ensureCursorVisible()

    def on_visualizer_clicked(self, btn_name):
        if btn_name == "LS":
            self.create_mapping_row("axes", "LeftX", {"type": "scroll_horizontal", "key": ""})
            self.create_mapping_row("axes", "LeftY", {"type": "scroll_vertical", "key": ""})
        elif btn_name == "RS":
            self.create_mapping_row("axes", "RightX", {"type": "mouse_x", "key": ""})
            self.create_mapping_row("axes", "RightY", {"type": "mouse_y", "key": ""})
        elif btn_name in ["LT", "RT"]:
            self.create_mapping_row("triggers", btn_name, {"type": "key_press", "key": ""})
        else:
            self.create_mapping_row("buttons", btn_name, {"type": "key_press", "key": ""})

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        # Using a default icon for now, should be replaced with a real icon
        self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        
        tray_menu = QMenu()
        show_action = QAction("Show Settings", self)
        show_action.triggered.connect(self.show)
        
        restart_action = QAction("Restart App", self)
        restart_action.triggered.connect(self.restart_app)
        
        autostart_action = QAction("Start with Windows", self, checkable=True)
        autostart_action.setChecked(self.check_autostart())
        autostart_action.triggered.connect(self.toggle_autostart)
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        
        tray_menu.addAction(show_action)
        tray_menu.addAction(restart_action)
        tray_menu.addAction(autostart_action)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def check_autostart(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "XboxControllerMapper")
            winreg.CloseKey(key)
            return True
        except OSError:
            return False

    def restart_app(self):
        print("Restarting application...")
        if hasattr(self, 'controller_thread') and self.controller_thread:
            self.controller_thread.running = False
            self.controller_thread.wait(1000)
            
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        
        QApplication.instance().quit()
        subprocess.Popen([sys.executable] + sys.argv)

    def toggle_autostart(self, enable):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            app_name = "XboxControllerMapper"
            if enable:
                exe_path = sys.executable
                script_path = os.path.abspath(__file__)
                exe_path = exe_path.replace("python.exe", "pythonw.exe")
                cmd = f'"{exe_path}" "{script_path}" --tray'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except OSError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to set auto-start: {e}")

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)
                
            haptic_state = self.config_data.get("haptic_enabled", True)
            self.haptic_checkbox.blockSignals(True)
            self.haptic_checkbox.setChecked(haptic_state)
            self.haptic_checkbox.blockSignals(False)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load config: {e}")
            self.config_data = {"profiles": {"Default": {"buttons": {}, "triggers": {}, "axes": {}}}}

        if "Global" not in self.config_data.get("profiles", {}):
            if "profiles" not in self.config_data:
                self.config_data["profiles"] = {}
            self.config_data["profiles"]["Global"] = {"buttons": {}, "triggers": {}, "axes": {}}

        # Legacy HUD support + multi-hud
        if "huds" not in self.config_data:
            if "hud_items" in self.config_data:
                self.config_data["huds"] = {"Default HUD": self.config_data.pop("hud_items")}
            else:
                self.config_data["huds"] = {"Default HUD": list(DEFAULT_HUD_ITEMS)}
        
        if not self.config_data["huds"]:
            self.config_data["huds"]["Default HUD"] = list(DEFAULT_HUD_ITEMS)

        # Populate HUD selector
        self.hud_dropdown.blockSignals(True)
        self.hud_dropdown.clear()
        self.hud_dropdown.addItems(self.config_data["huds"].keys())
        # Select active HUD or first one
        if self.current_hud_name in self.config_data["huds"]:
            self.hud_dropdown.setCurrentText(self.current_hud_name)
        else:
            self.current_hud_name = self.hud_dropdown.currentText()
        self.hud_dropdown.blockSignals(False)

        # Push to editor and preview
        active_items = self.config_data["huds"][self.current_hud_name]
        self.hud_menu.set_items(active_items)
        self._populate_hud_editor(active_items)

        self.mouse_spin.blockSignals(True)
        self.mouse_spin.setValue(self.config_data.get("mouse_speed", 15.0))
        self.mouse_spin.blockSignals(False)
        
        self.scroll_spin.blockSignals(True)
        self.scroll_spin.setValue(self.config_data.get("scroll_speed", 0.2))
        self.scroll_spin.blockSignals(False)

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(self.config_data.get("profiles", {}).keys())
        self.profile_combo.blockSignals(False)
        
        if self.profile_combo.count() > 0:
            self.profile_combo.setCurrentIndex(0)
            self.on_profile_changed(self.profile_combo.currentText())

    def on_profile_changed(self, profile_name):
        if not profile_name:
            return
            
        self.current_profile = profile_name
        self.clear_mapping_ui()
        
        profile_data = self.config_data["profiles"].get(profile_name, {})
        
        if profile_name in ["Default", "Global"]:
            self.bind_app_btn.setEnabled(False)
            self.bound_app_label.setText("Bound App: N/A (Global/Default)")
            self.bound_app_label.setStyleSheet("font-style: italic; color: #555555;")
        else:
            self.bind_app_btn.setEnabled(True)
            bound_app = profile_data.get("process_name", "")
            if bound_app:
                self.bound_app_label.setText(f"Bound App: {bound_app}")
                self.bound_app_label.setStyleSheet("font-style: italic; color: #43b7ff; font-weight: bold;")
            else:
                self.bound_app_label.setText("Bound App: None")
                self.bound_app_label.setStyleSheet("font-style: italic; color: #adaaaa; font-weight: bold;")
            
        for category in ["buttons", "triggers", "axes"]:
            items = profile_data.get(category, {})
            for key_name, action in items.items():
                self.create_mapping_row(category, key_name, action)

    def clear_mapping_ui(self):
        for i in reversed(range(self.mapping_layout.count())): 
            widget = self.mapping_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        self.mapping_fields.clear()

    def create_mapping_row(self, category, key_name, action):
        row_widget = QFrame()
        row_widget.setFrameShape(QFrame.StyledPanel)
        row_layout = QHBoxLayout(row_widget)
        
        cat_combo = NoScrollComboBox()
        cat_combo.addItems(["buttons", "triggers", "axes"])
        cat_combo.setCurrentText(category)
        
        key_input = QLineEdit(key_name)
        key_input.setPlaceholderText("Btn Name (e.g. A, LB+A)")
        
        type_combo = NoScrollComboBox()
        type_combo.addItems(["key_press", "key_tap", "mouse_x", "mouse_y", "scroll_vertical", "scroll_horizontal", "macro", "run_app", "radial_menu"])
        type_combo.setCurrentText(action.get("type", "key_press"))
        
        val_input = QLineEdit(action.get("key", ""))
        val_input.setPlaceholderText("Keyboard Key")
        
        remove_btn = QPushButton("X")
        remove_btn.setFixedWidth(30)
        remove_btn.clicked.connect(lambda: row_widget.setParent(None))
        
        row_layout.addWidget(cat_combo)
        row_layout.addWidget(key_input)
        row_layout.addWidget(type_combo)
        row_layout.addWidget(val_input)
        row_layout.addWidget(remove_btn)
        
        self.mapping_layout.addWidget(row_widget)
        self.mapping_fields.append((row_widget, cat_combo, key_input, type_combo, val_input))

    def add_mapping(self):
        self.create_mapping_row("buttons", "", {"type": "key_press", "key": ""})

    def add_profile(self):
        text, ok = QInputDialog.getText(self, 'Add Profile', 'Enter new profile name:')
        if ok and text:
            if text not in self.config_data["profiles"]:
                self.config_data["profiles"][text] = {"buttons": {}, "triggers": {}, "axes": {}}
                self.profile_combo.addItem(text)
                self.profile_combo.setCurrentText(text)

    def delete_profile(self):
        if self.current_profile and self.current_profile not in ["Default", "Global"]:
            del self.config_data["profiles"][self.current_profile]
            self.profile_combo.removeItem(self.profile_combo.currentIndex())
        else:
            QMessageBox.warning(self, "Warning", "Default and Global profiles cannot be deleted.")

    def bind_app_to_profile(self):
        if not self.current_profile or self.current_profile in ["Default", "Global"]:
            QMessageBox.warning(self, "Warning", "Cannot bind 'Default' or 'Global' profiles to a specific app. Create a custom profile first.")
            return
            
        dialog = ProcessSelectorDialog(self)
        if dialog.exec_() == QDialog.Accepted and dialog.selected_process:
            app_exe = dialog.selected_process
            self.config_data["profiles"][self.current_profile]["process_name"] = app_exe
            self.save_config()
            self.on_profile_changed(self.current_profile)

    def save_config(self):
        if not self.current_profile:
            return
            
        # Extract data from UI for current profile
        new_profile_data = {"buttons": {}, "triggers": {}, "axes": {}}
        
        # Preserve process_name if it exists
        old_profile_data = self.config_data["profiles"].get(self.current_profile, {})
        if "process_name" in old_profile_data:
            new_profile_data["process_name"] = old_profile_data["process_name"]
            
        for widget, cat_combo, key_input, type_combo, val_input in self.mapping_fields:
            if widget.parent() is None: # Removed row
                continue
                
            cat = cat_combo.currentText()
            key_name = key_input.text().strip()
            act_type = type_combo.currentText()
            act_val = val_input.text().strip()
            
            if key_name and (act_val or cat == "axes" or act_type == "radial_menu"):
                if act_val:
                    new_profile_data[cat][key_name] = {"type": act_type, "key": act_val}
                else:
                    new_profile_data[cat][key_name] = {"type": act_type}
                
        self.config_data["profiles"][self.current_profile] = new_profile_data
        self.config_data["haptic_enabled"] = self.haptic_checkbox.isChecked()
        self.config_data["mouse_speed"] = self.mouse_spin.value()
        self.config_data["scroll_speed"] = self.scroll_spin.value()
        
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
            # Hot reload controller mapping thread
            self.controller_thread.reload_config()
            QMessageBox.information(self, "Success", "Configuration saved!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def assign_preset(self):
        selected = self.preset_tree.selectedItems()
        if not selected or not selected[0].data(0, Qt.UserRole):
            QMessageBox.warning(self, "Error", "Please select an action from the library first.")
            return
            
        if not self.current_profile:
            QMessageBox.warning(self, "Error", "No profile selected in Configuration tab. Please create one.")
            return
            
        preset_data = selected[0].data(0, Qt.UserRole)
        btn_name = self.assign_btn_combo.currentText()
        
        if btn_name in ["LT", "RT"]:
            category = "triggers"
        elif btn_name in ["LeftX", "LeftY", "RightX", "RightY"]:
            category = "axes"
        else:
            category = "buttons"
            
        profile_data = self.config_data["profiles"].get(self.current_profile, {})
        if category not in profile_data:
            profile_data[category] = {}
            
        profile_data[category][btn_name] = preset_data
        
        # Automatically save after applying preset
        self.config_data["profiles"][self.current_profile] = profile_data
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
            self.controller_thread.reload_config()
            
            # Refresh the UI rows
            self.on_profile_changed(self.current_profile)
            self.tabs.setCurrentIndex(0) # Jump back to config tab
            QMessageBox.information(self, "Success", f"Preset assigned to '{btn_name}'.\nSwitched back to Configuration view.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply preset: {e}")

    # ------------------------------------------------------------------ #
    #  HUD SETTINGS TAB
    # ------------------------------------------------------------------ #
    def _build_hud_settings_tab(self):
        hud_tab = QWidget()
        hud_outer_layout = QVBoxLayout(hud_tab)
        
        # --- Top Bar: HUD Selector & Controls ---
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Select HUD:"))
        
        self.hud_dropdown = NoScrollComboBox()
        self.hud_dropdown.currentIndexChanged.connect(self._on_hud_selection_changed)
        selector_layout.addWidget(self.hud_dropdown, 1)

        add_hud_btn = QPushButton("➕ Add HUD")
        add_hud_btn.clicked.connect(self._add_new_hud)
        selector_layout.addWidget(add_hud_btn)

        rename_hud_btn = QPushButton("✎ Rename")
        rename_hud_btn.clicked.connect(self._rename_current_hud)
        selector_layout.addWidget(rename_hud_btn)

        delete_hud_btn = QPushButton("🗑 Delete")
        delete_hud_btn.clicked.connect(self._delete_current_hud)
        selector_layout.addWidget(delete_hud_btn)
        
        hud_outer_layout.addLayout(selector_layout)

        # --- Main Layout: Preview + Editors ---
        hud_main_layout = QHBoxLayout()

        # --- Left: Live Preview ---
        preview_layout = QVBoxLayout()
        preview_label = QLabel("Live Preview")
        preview_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #4DAAFE;")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_label)

        self.hud_preview = RadialMenuWidget()
        self.hud_preview.setWindowFlags(Qt.Widget)  # Embed as normal widget (not overlay)
        self.hud_preview.setAttribute(Qt.WA_TranslucentBackground, False)
        self.hud_preview.setFixedSize(380, 380)
        self.hud_preview.setStyleSheet("background-color: #1A1A1E; border-radius: 8px;")
        preview_layout.addWidget(self.hud_preview, alignment=Qt.AlignCenter)
        preview_layout.addStretch()
        hud_main_layout.addLayout(preview_layout, 4)

        # --- Right: Slot Editors ---
        editor_layout = QVBoxLayout()
        editor_header = QLabel("HUD Slot Configuration")
        editor_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #4DAAFE;")
        editor_layout.addWidget(editor_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: transparent;")
        self.hud_editor_layout = QVBoxLayout(scroll_widget)
        self.hud_editor_layout.setAlignment(Qt.AlignTop)

        self.hud_slot_fields = []  # list of tuples

        for i in range(8):
            slot_frame = QFrame()
            slot_frame.setFrameShape(QFrame.StyledPanel)
            slot_frame.setStyleSheet("QFrame { background-color: #2A2A2E; border: 1px solid #3A3A3E; border-radius: 4px; margin: 2px; }")
            
            frame_layout = QVBoxLayout(slot_frame)
            frame_layout.setContentsMargins(5, 5, 5, 5)
            frame_layout.setSpacing(4)

            # --- Row 1: Basic Input ---
            row1 = QHBoxLayout()
            row1.setContentsMargins(0, 0, 0, 0)
            
            dir_label = QLabel(f"Slot {i+1}")
            dir_label.setFixedWidth(45)
            dir_label.setStyleSheet("font-weight: bold; color: #8A8A9A;")
            dir_label.setToolTip(SLOT_DIRECTIONS[i])

            icon_input = QLineEdit()
            icon_input.setPlaceholderText("Icon")
            icon_input.setFixedWidth(45)
            icon_input.setAlignment(Qt.AlignCenter)
            icon_input.setToolTip("Emoji icon (e.g. 🎵)")

            label_input = QLineEdit()
            label_input.setPlaceholderText("Label")
            label_input.setMinimumWidth(80)

            type_combo = NoScrollComboBox()
            type_combo.addItems(["key_press", "key_tap", "macro", "run_app"])
            type_combo.setFixedWidth(100)

            key_input = QLineEdit()
            key_input.setPlaceholderText("Key / Path")
            key_input.setMinimumWidth(100)

            row1.addWidget(dir_label)
            row1.addWidget(icon_input)
            row1.addWidget(label_input)
            row1.addWidget(type_combo)
            row1.addWidget(key_input)

            # --- Row 2: Hold & Repeat Settings ---
            row2 = QHBoxLayout()
            row2.setContentsMargins(50, 0, 0, 0) # Indent
            row2.setSpacing(10)

            hold_cb = QCheckBox("Hold Exec")
            hold_cb.setToolTip("Execute action while holding stick on this slot")
            
            hold_delay_spin = QDoubleSpinBox()
            hold_delay_spin.setRange(0.1, 5.0)
            hold_delay_spin.setSingleStep(0.1)
            hold_delay_spin.setSuffix("s delay")
            hold_delay_spin.setMinimumWidth(85)
            hold_delay_spin.setValue(0.5)
            
            repeat_cb = QCheckBox("Repeat")
            repeat_cb.setToolTip("Continually repeat action while held")

            repeat_interval_spin = QDoubleSpinBox()
            repeat_interval_spin.setRange(0.01, 2.0)
            repeat_interval_spin.setSingleStep(0.05)
            repeat_interval_spin.setSuffix("s intvl")
            repeat_interval_spin.setMinimumWidth(95)
            repeat_interval_spin.setValue(0.2)
            
            # Interactive linkage
            hold_cb.toggled.connect(hold_delay_spin.setEnabled)
            hold_cb.toggled.connect(repeat_cb.setEnabled)
            repeat_cb.toggled.connect(repeat_interval_spin.setEnabled)
            
            row2.addWidget(hold_cb)
            row2.addWidget(hold_delay_spin)
            row2.addWidget(repeat_cb)
            row2.addWidget(repeat_interval_spin)
            row2.addStretch()

            frame_layout.addLayout(row1)
            frame_layout.addLayout(row2)

            self.hud_editor_layout.addWidget(slot_frame)
            self.hud_slot_fields.append((icon_input, label_input, type_combo, key_input, hold_cb, hold_delay_spin, repeat_cb, repeat_interval_spin))

        scroll.setWidget(scroll_widget)
        editor_layout.addWidget(scroll)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        save_hud_btn = QPushButton("💾 Save HUD Config")
        save_hud_btn.setStyleSheet("background-color: #238636; padding: 8px 16px;")
        save_hud_btn.clicked.connect(self._save_hud_config)

        preview_btn = QPushButton("👁️ Update Preview")
        preview_btn.clicked.connect(self._update_hud_preview)

        reset_hud_btn = QPushButton("↩️ Reset to Defaults")
        reset_hud_btn.setStyleSheet("background-color: #A31515; padding: 8px 16px;")
        reset_hud_btn.clicked.connect(self._reset_hud_defaults)

        btn_layout.addWidget(preview_btn)
        btn_layout.addWidget(save_hud_btn)
        btn_layout.addWidget(reset_hud_btn)
        editor_layout.addLayout(btn_layout)

        hud_main_layout.addLayout(editor_layout, 6)
        hud_outer_layout.addLayout(hud_main_layout, 1)
        self.tabs.addTab(hud_tab, "🎯 HUD SETTINGS")

    def _populate_hud_editor(self, items):
        """Fill the 8 editor rows from an items list."""
        for i, fields in enumerate(self.hud_slot_fields):
            icon_input, label_input, type_combo, key_input, hold_cb, hold_delay_spin, repeat_cb, repeat_interval_spin = fields
            item = items[i] if i < len(items) else {}
            icon_input.setText(item.get("icon", ""))
            label_input.setText(item.get("label", ""))
            action = item.get("action", {})
            act_type = action.get("type", "key_press")
            idx = type_combo.findText(act_type)
            if idx >= 0:
                type_combo.setCurrentIndex(idx)
            key_input.setText(action.get("key", ""))
            
            hold_cb.setChecked(item.get("hold_execute", False))
            hold_delay_spin.setValue(item.get("hold_delay_s", 0.5))
            hold_delay_spin.setEnabled(item.get("hold_execute", False))
            
            repeat_cb.setChecked(item.get("hold_repeat", False))
            repeat_cb.setEnabled(item.get("hold_execute", False))
            
            repeat_interval_spin.setValue(item.get("hold_repeat_s", 0.2))
            repeat_interval_spin.setEnabled(item.get("hold_repeat", False))

        # Also update preview
        self.hud_preview.set_items(items)
        self.hud_preview.selected_index = 6  # Show "Up" slot highlighted for demo
        self.hud_preview.update()

    def _collect_hud_items(self):
        """Read the 8 editor rows and return a list of HUD item dicts."""
        items = []
        for fields in self.hud_slot_fields:
            icon_input, label_input, type_combo, key_input, hold_cb, hold_delay_spin, repeat_cb, repeat_interval_spin = fields
            item = {
                "label": label_input.text().strip(),
                "icon": icon_input.text().strip(),
                "hold_execute": hold_cb.isChecked(),
                "hold_delay_s": hold_delay_spin.value(),
                "hold_repeat": repeat_cb.isChecked(),
                "hold_repeat_s": repeat_interval_spin.value(),
                "action": {
                    "type": type_combo.currentText(),
                    "key": key_input.text().strip()
                }
            }
            items.append(item)
        return items

    def _update_hud_preview(self):
        items = self._collect_hud_items()
        self.hud_preview.set_items(items)
        self.hud_preview.update()

    def _save_hud_config(self):
        items = self._collect_hud_items()
        self.config_data.setdefault("huds", {})[self.current_hud_name] = items

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
            # Hot-reload: update the live overlay HUD + controller thread
            self.hud_menu.set_items(items)
            self.controller_thread.reload_config()
            self._update_hud_preview()
            QMessageBox.information(self, "Success", f"HUD '{self.current_hud_name}' saved!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save HUD config: {e}")

    def _reset_hud_defaults(self):
        reply = QMessageBox.question(self, "Reset HUD",
                                     f"Reset '{self.current_hud_name}' to defaults?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._populate_hud_editor(list(DEFAULT_HUD_ITEMS))

    def _on_hud_selection_changed(self, idx):
        if idx >= 0:
            # Auto-save old HUD before switching
            old_items = self._collect_hud_items()
            if self.current_hud_name in self.config_data.get("huds", {}):
                self.config_data["huds"][self.current_hud_name] = old_items

            self.current_hud_name = self.hud_dropdown.currentText()
            items = self.config_data["huds"].get(self.current_hud_name, list(DEFAULT_HUD_ITEMS))
            self._populate_hud_editor(items)

    def _add_new_hud(self):
        name, ok = QInputDialog.getText(self, "New HUD", "Enter a name for the new HUD:")
        if ok and name:
            name = name.strip()
            if not name or name in self.config_data.get("huds", {}):
                QMessageBox.warning(self, "Error", "Invalid or duplicate HUD name.")
                return
                
            self.config_data.setdefault("huds", {})[name] = list(DEFAULT_HUD_ITEMS)
            
            # Save config to persist
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.config_data, f, indent=4, ensure_ascii=False)
                self.controller_thread.reload_config()
                
                self.hud_dropdown.blockSignals(True)
                self.hud_dropdown.addItem(name)
                self.hud_dropdown.setCurrentText(name)
                self.hud_dropdown.blockSignals(False)
                self.current_hud_name = name
                self._populate_hud_editor(list(DEFAULT_HUD_ITEMS))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add HUD: {e}")

    def _rename_current_hud(self):
        if self.current_hud_name == "Default HUD":
            QMessageBox.information(self, "Rename", "Cannot rename the Default HUD.")
            return

        name, ok = QInputDialog.getText(self, "Rename HUD", "Enter new name:", text=self.current_hud_name)
        if ok and name:
            name = name.strip()
            if not name or name == self.current_hud_name or name in self.config_data.get("huds", {}):
                QMessageBox.warning(self, "Error", "Invalid or duplicate HUD name.")
                return
            
            # Move items
            items = self.config_data["huds"].pop(self.current_hud_name)
            self.config_data["huds"][name] = items
            
            # Save config
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.config_data, f, indent=4, ensure_ascii=False)
                self.controller_thread.reload_config()
                
                # Update UI
                idx = self.hud_dropdown.findText(self.current_hud_name)
                self.hud_dropdown.blockSignals(True)
                self.hud_dropdown.setItemText(idx, name)
                self.hud_dropdown.blockSignals(False)
                
                self.current_hud_name = name
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to rename HUD: {e}")

    def _delete_current_hud(self):
        if self.current_hud_name == "Default HUD":
            QMessageBox.information(self, "Delete", "Cannot delete the Default HUD.")
            return

        reply = QMessageBox.question(self, "Delete HUD",
                                     f"Are you sure you want to delete '{self.current_hud_name}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.config_data["huds"].pop(self.current_hud_name, None)
            
            # Save config
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.config_data, f, indent=4, ensure_ascii=False)
                self.controller_thread.reload_config()
                
                # Update UI
                idx = self.hud_dropdown.findText(self.current_hud_name)
                self.hud_dropdown.blockSignals(True)
                self.hud_dropdown.removeItem(idx)
                self.hud_dropdown.blockSignals(False)
                
                self.current_hud_name = self.hud_dropdown.currentText()
                items = self.config_data["huds"].get(self.current_hud_name, list(DEFAULT_HUD_ITEMS))
                self._populate_hud_editor(items)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete HUD: {e}")

    def closeEvent(self, event):
        # Minimize to tray instead of closing
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Xbox Controller Mapper",
            "Application minimized to tray.",
            QSystemTrayIcon.Information,
            2000
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Keep running when window is closed (tray)
    window = ConfigUI()
    
    # Ensure thread stops gracefully on app quit
    app.aboutToQuit.connect(window.controller_thread.stop)
    
    if "--tray" not in sys.argv:
        window.show()
    sys.exit(app.exec_())
