import math
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import (QPainter, QColor, QPen, QFont, QBrush,
                          QRadialGradient, QConicalGradient, QPainterPath)
from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF

# Direction labels for each slot index (0=Right, going clockwise)
SLOT_DIRECTIONS = ["Right", "Down-Right", "Down", "Down-Left", "Left", "Up-Left", "Up", "Up-Right"]

# Define global HUD items for use in controller_mapper.py as well
DEFAULT_HUD_ITEMS = [
    {"label": "Next Track",  "icon": "⏭️", "hold_execute": False, "hold_delay_s": 0.5, "hold_repeat": False, "hold_repeat_s": 0.2, "action": {"type":"key_press", "key":"next_track"}},     # 0: Right
    {"label": "Calculator",  "icon": "🧮", "hold_execute": False, "hold_delay_s": 0.5, "hold_repeat": False, "hold_repeat_s": 0.2, "action": {"type":"run_app", "key":"calc.exe"}},          # 1: Down-Right
    {"label": "Vol Down",    "icon": "🔉", "hold_execute": True, "hold_delay_s": 0.5, "hold_repeat": True, "hold_repeat_s": 0.2, "action": {"type":"key_press", "key":"volume_down"}},      # 2: Down
    {"label": "Notepad",     "icon": "📝", "hold_execute": False, "hold_delay_s": 0.5, "hold_repeat": False, "hold_repeat_s": 0.2, "action": {"type":"run_app", "key":"notepad.exe"}},        # 3: Down-Left
    {"label": "Prev Track",  "icon": "⏮️", "hold_execute": False, "hold_delay_s": 0.5, "hold_repeat": False, "hold_repeat_s": 0.2, "action": {"type":"key_press", "key":"prev_track"}},      # 4: Left
    {"label": "Play/Pause",  "icon": "⏯️", "hold_execute": False, "hold_delay_s": 0.5, "hold_repeat": False, "hold_repeat_s": 0.2, "action": {"type":"key_press", "key":"play_pause"}},      # 5: Up-Left
    {"label": "Vol Up",      "icon": "🔊", "hold_execute": True, "hold_delay_s": 0.5, "hold_repeat": True, "hold_repeat_s": 0.2, "action": {"type":"key_press", "key":"volume_up"}},        # 6: Up
    {"label": "Mute",        "icon": "🔇", "hold_execute": False, "hold_delay_s": 0.5, "hold_repeat": False, "hold_repeat_s": 0.2, "action": {"type":"key_press", "key":"volume_mute"}},      # 7: Up-Right
]


class RadialMenuWidget(QWidget):
    def __init__(self, items=None):
        super().__init__()
        self.items = items if items is not None else list(DEFAULT_HUD_ITEMS)
        self.selected_index = -1

        # Overlay settings: transparent background, stay on top, borderless
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.resize(700, 700)

    def set_items(self, items):
        """Hot-reload HUD items from config."""
        self.items = items if items else list(DEFAULT_HUD_ITEMS)
        self.update()

    def show_hud(self):
        # Center globally on screen
        desktop_rect = QApplication.desktop().screenGeometry()
        self.move((desktop_rect.width() - self.width()) // 2,
                  (desktop_rect.height() - self.height()) // 2)
        self.show()

    def hide_hud(self):
        self.hide()

    def update_selection(self, angle_deg):
        if angle_deg < 0:
            self.selected_index = -1
        else:
            shifted = (angle_deg + 22.5) % 360
            self.selected_index = int(shifted // 45)
        self.update()

    # ------------------------------------------------------------------ #
    #  PAINTING
    # ------------------------------------------------------------------ #
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Auto-scale: design is 700x700, scale to actual widget size
        design_size = 700.0
        scale = min(self.width(), self.height()) / design_size
        painter.scale(scale, scale)

        cx = design_size / 2.0
        cy = design_size / 2.0
        center = QPointF(cx, cy)
        outer_r = 280.0
        inner_r = 90.0

        # --- Subtle outer glow ring ---
        glow_pen = QPen(QColor(60, 140, 255, 50), 4)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, outer_r + 2, outer_r + 2)

        # --- Draw 8 donut slices ---
        for i in range(8):
            self._draw_slice(painter, center, outer_r, inner_r, i)

        # --- Separator lines between slices ---
        painter.setPen(QPen(QColor(80, 80, 80, 120), 1.5))
        for i in range(8):
            angle_rad = math.radians(i * 45 - 22.5)
            x1 = cx + inner_r * math.cos(angle_rad)
            y1 = cy + inner_r * math.sin(angle_rad)
            x2 = cx + outer_r * math.cos(angle_rad)
            y2 = cy + outer_r * math.sin(angle_rad)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # --- Center dark circle ---
        center_grad = QRadialGradient(center, inner_r)
        center_grad.setColorAt(0.0, QColor(20, 20, 25, 245))
        center_grad.setColorAt(0.85, QColor(30, 30, 35, 240))
        center_grad.setColorAt(1.0, QColor(45, 45, 50, 230))
        painter.setBrush(QBrush(center_grad))
        painter.setPen(QPen(QColor(70, 130, 220, 100), 2.5))
        painter.drawEllipse(center, inner_r, inner_r)

        # --- Crosshair in center ---
        painter.setPen(QPen(QColor(100, 160, 240, 70), 1))
        ch = 18
        painter.drawLine(QPointF(cx - ch, cy), QPointF(cx + ch, cy))
        painter.drawLine(QPointF(cx, cy - ch), QPointF(cx, cy + ch))
        # Small dot in center
        painter.setBrush(QColor(100, 160, 240, 90))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, 3, 3)

        # --- Draw Icons & Labels ---
        mid_r = (inner_r + outer_r) / 2.0  # ~185
        for i in range(8):
            angle_rad = math.radians(i * 45)
            tx = cx + mid_r * math.cos(angle_rad)
            ty = cy + mid_r * math.sin(angle_rad)

            item = self.items[i] if i < len(self.items) else {}
            icon = item.get("icon", "")
            label = item.get("label", "")

            is_selected = (i == self.selected_index)

            # -- Icon (emoji) --
            if icon:
                icon_font = QFont("Segoe UI Emoji", 22)
                painter.setFont(icon_font)
                icon_rect = QRectF(tx - 30, ty - 28, 60, 36)
                # Shadow
                painter.setPen(QColor(0, 0, 0, 120))
                painter.drawText(icon_rect.adjusted(1, 1, 1, 1), Qt.AlignCenter, icon)
                # Foreground
                painter.setPen(QColor(255, 255, 255, 255 if is_selected else 220))
                painter.drawText(icon_rect, Qt.AlignCenter, icon)

            # -- Label --
            if label:
                label_font = QFont("Segoe UI", 10, QFont.Bold if is_selected else QFont.DemiBold)
                painter.setFont(label_font)
                label_rect = QRectF(tx - 55, ty + 8, 110, 30)
                # Shadow
                painter.setPen(QColor(0, 0, 0, 160))
                painter.drawText(label_rect.adjusted(1, 1, 1, 1), Qt.AlignCenter | Qt.TextWordWrap, label)
                # Foreground
                if is_selected:
                    painter.setPen(QColor(180, 220, 255, 255))
                else:
                    painter.setPen(QColor(210, 210, 215, 230))
                painter.drawText(label_rect, Qt.AlignCenter | Qt.TextWordWrap, label)

    def _draw_slice(self, painter, center, outer_r, inner_r, index):
        """Draw a single annular (donut) slice using QPainterPath."""
        start_deg = index * 45 - 22.5
        span_deg = 45.0
        is_selected = (index == self.selected_index)

        # Build donut path
        path = QPainterPath()
        outer_rect = QRectF(center.x() - outer_r, center.y() - outer_r,
                            outer_r * 2, outer_r * 2)
        inner_rect = QRectF(center.x() - inner_r, center.y() - inner_r,
                            inner_r * 2, inner_r * 2)

        # Outer arc (clockwise)
        path.arcMoveTo(outer_rect, -start_deg)
        path.arcTo(outer_rect, -start_deg, -span_deg)

        # Line to inner arc
        end_angle_rad = math.radians(start_deg + span_deg)
        path.lineTo(center.x() + inner_r * math.cos(end_angle_rad),
                     center.y() + inner_r * math.sin(end_angle_rad))

        # Inner arc (counter-clockwise back)
        path.arcTo(inner_rect, -(start_deg + span_deg), span_deg)
        path.closeSubpath()

        # --- Fill ---
        if is_selected:
            # Vibrant blue radial gradient with glow
            grad = QRadialGradient(center, outer_r)
            grad.setColorAt(0.0, QColor(0, 90, 180, 200))
            grad.setColorAt(0.35, QColor(0, 110, 210, 220))
            grad.setColorAt(0.7, QColor(20, 140, 240, 235))
            grad.setColorAt(1.0, QColor(40, 160, 255, 200))
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor(80, 180, 255, 180), 1.5))
        else:
            # Dark subtle gradient
            grad = QRadialGradient(center, outer_r)
            grad.setColorAt(0.0, QColor(22, 22, 28, 210))
            grad.setColorAt(0.5, QColor(30, 30, 38, 205))
            grad.setColorAt(1.0, QColor(40, 40, 50, 195))
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor(55, 55, 65, 100), 0.5))

        painter.drawPath(path)
