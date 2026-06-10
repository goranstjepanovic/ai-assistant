import math
import queue
import threading

from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPixmap, QRadialGradient, QPen, QBrush, QPainterPath,
    QIcon, QAction,
)

IDLE = "idle"
LISTENING = "listening"
PROCESSING = "processing"
SPEAKING = "speaking"
FOLLOW_UP = "follow_up"
MUTED = "muted"

# Near-black warm background
_BG = QColor(8, 4, 4, 200)

# Deep crimson palette — all states stay in the red family
_RGB = {
    IDLE:       (55,  10, 10),
    LISTENING:  (205, 28, 42),
    PROCESSING: (155, 20, 32),
    SPEAKING:   (220, 32, 50),
    FOLLOW_UP:  (90,  18, 28),
    MUTED:      (35,  35, 35),
}

# Per-bar phase offsets so bars animate independently
_BAR_OFFSETS = [i * 0.73 + (i % 3) * 0.31 for i in range(11)]


def _c(rgb: tuple, alpha: int) -> QColor:
    return QColor(rgb[0], rgb[1], rgb[2], max(0, min(255, alpha)))


_SYMBOL_RENDER_SIZE = 256   # pre-scale once at startup; draw time just blits


def _load_symbol_pixmap(path: str) -> QPixmap | None:
    if not path:
        return None
    import logging
    px = QPixmap(path)
    if px.isNull():
        logging.getLogger(__name__).warning("Could not load symbol image: %s", path)
        return None
    # If the image has no alpha channel (flat JPEG / opaque PNG) try to remove
    # the white background via Pillow luminosity inversion.
    if not px.hasAlphaChannel():
        try:
            from PIL import Image, ImageOps
            import io
            img = Image.open(path).convert("RGBA")
            img.putalpha(ImageOps.invert(img.convert("L")))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px2 = QPixmap()
            px2.loadFromData(buf.getvalue())
            if not px2.isNull():
                px = px2
        except Exception as exc:
            logging.getLogger(__name__).warning("White-bg removal failed for %s: %s", path, exc)
    # Pre-scale once with Qt's smooth transform so draw-time blits stay crisp.
    return px.scaled(
        _SYMBOL_RENDER_SIZE, _SYMBOL_RENDER_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _make_tray_icon(muted: bool) -> QIcon:
    px = QPixmap(22, 22)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(80, 80, 80) if muted else QColor(205, 28, 42)
    p.setBrush(QBrush(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 18, 18)
    if muted:
        # Draw a small diagonal line to indicate muted
        p.setPen(QPen(QColor(180, 180, 180), 2.5,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(6, 6, 16, 16)
    p.end()
    return QIcon(px)


class OverlayWidget(QWidget):
    def __init__(self, ui_queue: queue.Queue, symbol_path: str = "",
                 mute_flag: threading.Event | None = None):
        super().__init__()
        self._queue = ui_queue
        self._mute_flag = mute_flag
        self._symbol_pixmap: QPixmap | None = _load_symbol_pixmap(symbol_path)
        self._state = IDLE
        self._level = 0.0
        self._phase = 0.0
        self._ripples: list[float] = []
        self._drag_pos = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(160, 160)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - 180, screen.bottom() - 190)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)
        self.show()

        self._setup_tray()

    # ── System tray ───────────────────────────────────────────────────────────

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(_make_tray_icon(False))
        self._tray.setToolTip("Nyssa")

        menu = QMenu()

        self._vis_action = QAction("Hide Nyssa", self)
        self._vis_action.triggered.connect(self._toggle_visibility)
        menu.addAction(self._vis_action)

        self._mute_action = QAction("Mute", self)
        self._mute_action.triggered.connect(self._toggle_mute)
        menu.addAction(self._mute_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
            self._vis_action.setText("Show Nyssa")
        else:
            self.show()
            self._vis_action.setText("Hide Nyssa")

    def _toggle_mute(self):
        if self._mute_flag is None:
            return
        if self._mute_flag.is_set():
            self._mute_flag.clear()
            self._mute_action.setText("Mute")
            self._tray.setIcon(_make_tray_icon(False))
            self._tray.setToolTip("Nyssa")
            self._state = IDLE
        else:
            self._mute_flag.set()
            self._mute_action.setText("Unmute")
            self._tray.setIcon(_make_tray_icon(True))
            self._tray.setToolTip("Nyssa (Muted)")
            self._state = MUTED
            self._ripples = []

    # ── Drag ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── Tick ─────────────────────────────────────────────────────────────────

    def _tick(self):
        while True:
            try:
                kind, value = self._queue.get_nowait()
                if kind == "state":
                    # Don't overwrite muted state with backend signals
                    if self._state == MUTED:
                        pass
                    elif value != self._state:
                        self._state = value
                        self._phase = 0.0
                        if value not in (IDLE, MUTED):
                            self._ripples.append(0.0)
                elif kind == "level":
                    boosted = min(1.0, float(value) * 5.0)
                    if boosted > self._level:
                        self._level = boosted
            except queue.Empty:
                break

        speed = 0.10 if self._state == PROCESSING else 0.055
        self._phase += speed
        if self._phase > 6000.0:
            self._phase -= 6000.0

        self._level = max(0.0, self._level - 0.05)

        self._ripples = [r + 0.020 for r in self._ripples if r < 1.0]

        if self._state == LISTENING and self._level > 0.15:
            if not self._ripples or self._ripples[-1] > 0.30:
                self._ripples.append(0.0)
        elif self._state == SPEAKING:
            speech = abs(0.35 * math.sin(self._phase * 3.7) + 0.20 * math.sin(self._phase * 7.3))
            if speech > 0.35 and (not self._ripples or self._ripples[-1] > 0.42):
                self._ripples.append(0.0)
        elif self._state == PROCESSING:
            if not self._ripples or self._ripples[-1] > 0.55:
                self._ripples.append(0.0)

        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        outer = min(w, h) / 2.0 - 6

        rgb = _RGB.get(self._state, _RGB[IDLE])

        # Background disk with subtle radial gradient
        grad = QRadialGradient(QPointF(cx, cy), outer)
        grad.setColorAt(0.0, QColor(14, 6, 6, 195))
        grad.setColorAt(1.0, QColor(4,  2, 2, 215))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), outer, outer)

        # Thin border ring
        border_a = 30 if self._state == IDLE else 55
        p.setPen(QPen(_c(rgb, border_a), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), outer, outer)

        # Ripple rings
        for r in self._ripples:
            ring_r = outer * (0.50 + 0.50 * r)
            alpha = int(90 * (1.0 - r))
            p.setPen(QPen(_c(rgb, alpha), 1.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # Symbol brightness varies by state and audio level
        if self._state in (IDLE, MUTED):
            sym_a = int(75 + 12 * math.sin(self._phase))
        elif self._state == PROCESSING:
            sym_a = int(175 + 45 * math.sin(self._phase * 2.5))
        else:
            sym_a = int(200 + 40 * self._level)

        self._draw_symbol(p, cx, cy, outer * 0.86, _c(rgb, min(255, sym_a)))

        # Spinning arc for processing
        if self._state == PROCESSING:
            p.setPen(QPen(_c(rgb, 130), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            ar = outer * 0.88
            rect = QRectF(cx - ar, cy - ar, ar * 2, ar * 2)
            start = int((self._phase * 180.0 / math.pi * 16) % (360 * 16))
            p.drawArc(rect, start, int(210 * 16))

        # Waveform bars for listening / speaking (not during follow-up or muted)
        if self._state in (LISTENING, SPEAKING):
            self._draw_bars(p, cx, cy + outer * 0.45, outer, rgb)

        p.end()

    # ── Symbol ────────────────────────────────────────────────────────────────

    def _draw_symbol(self, p: QPainter, cx: float, cy: float,
                     size: float, color: QColor):
        if self._symbol_pixmap is not None:
            self._draw_symbol_image(p, cx, cy, size, color)
        else:
            self._draw_symbol_trident(p, cx, cy, size, color)

    def _draw_symbol_image(self, p: QPainter, cx: float, cy: float,
                           size: float, color: QColor):
        sz = int(round(size * 2))
        x  = int(round(cx - size))
        y  = int(round(cy - size))
        p.setOpacity(color.alphaF())
        p.drawPixmap(x, y, sz, sz, self._symbol_pixmap)
        p.setOpacity(1.0)

    def _draw_symbol_trident(self, p: QPainter, cx: float, cy: float,
                             size: float, color: QColor):
        s = size

        # Teardrop (filled) at top
        td_cx = cx
        td_cy = cy - s * 0.32
        td_rx = s * 0.075
        td_ry = s * 0.125

        drop = QPainterPath()
        drop.moveTo(td_cx, td_cy - td_ry)
        drop.cubicTo(
            td_cx + td_rx * 1.3, td_cy - td_ry * 0.3,
            td_cx + td_rx,       td_cy + td_ry * 0.5,
            td_cx,               td_cy + td_ry,
        )
        drop.cubicTo(
            td_cx - td_rx,       td_cy + td_ry * 0.5,
            td_cx - td_rx * 1.3, td_cy - td_ry * 0.3,
            td_cx,               td_cy - td_ry,
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(drop)

        # Arms and stem (stroked)
        pen_w = max(1.8, s * 0.043)
        pen = QPen(color, pen_w, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        jx, jy = cx, cy - s * 0.04  # arm junction

        # Left arm
        la = QPainterPath()
        la.moveTo(jx, jy)
        la.cubicTo(
            jx - s * 0.12, jy - s * 0.13,
            jx - s * 0.29, jy - s * 0.17,
            jx - s * 0.38, jy - s * 0.07,
        )
        p.drawPath(la)

        # Right arm (mirror)
        ra = QPainterPath()
        ra.moveTo(jx, jy)
        ra.cubicTo(
            jx + s * 0.12, jy - s * 0.13,
            jx + s * 0.29, jy - s * 0.17,
            jx + s * 0.38, jy - s * 0.07,
        )
        p.drawPath(ra)

        # Stem: from just below teardrop bottom down to a sharp bottom point
        stem = QPainterPath()
        stem.moveTo(cx, td_cy + td_ry + pen_w * 0.6)
        stem.lineTo(cx, cy + s * 0.40)
        p.drawPath(stem)

    # ── Waveform bars ─────────────────────────────────────────────────────────

    def _draw_bars(self, p: QPainter, base_cx: float, base_y: float,
                   outer: float, rgb: tuple):
        n = 11
        bar_w = outer * 0.062
        gap = outer * 0.114
        start_x = base_cx - gap * (n - 1) / 2
        max_h = outer * 0.30

        if self._state == SPEAKING:
            drive = abs(
                0.40 * math.sin(self._phase * 3.7)
                + 0.28 * math.sin(self._phase * 7.3)
                + 0.18 * math.sin(self._phase * 1.9)
            )
        else:
            # Gentle idle pulse so bars animate while waiting for speech
            idle_pulse = 0.10 * abs(math.sin(self._phase * 1.1))
            drive = max(self._level, idle_pulse)

        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            off = _BAR_OFFSETS[i]
            animated = 0.5 + 0.5 * abs(math.sin(self._phase * (2.1 + i * 0.38) + off))
            raw_h = max_h * drive * animated
            # Taper bars toward the edges
            center_pos = abs((i - (n - 1) / 2) / ((n - 1) / 2))
            raw_h *= (1.0 - 0.35 * center_pos)
            h = max(outer * 0.022, raw_h)

            x = start_x + i * gap
            rect = QRectF(x - bar_w / 2, base_y - h, bar_w, h)
            alpha = int(150 + 80 * drive)
            p.setBrush(QBrush(_c(rgb, min(255, alpha))))
            p.drawRoundedRect(rect, bar_w / 2, bar_w / 2)
