"""Logo dell'app, ispirato all'icona Promemoria di iPhone.

Quadrato bianco arrotondato con tre righe: pallino colorato (blu, rosso, arancio)
e una linea grigia, come una lista di cose da fare.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap

ROW_COLORS = ("#0A84FF", "#FF453A", "#FF9F0A")
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
ICO_PATH = Path(__file__).parent / "assets" / "promemoria.ico"


def render_logo(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)

    # sfondo: "squircle" bianco con bordo leggero (visibile anche su barra chiara)
    margin = max(0.5, s * 0.03)
    body = QRectF(margin, margin, s - 2 * margin, s - 2 * margin)
    radius = body.width() * 0.235
    p.setPen(QPen(QColor(0, 0, 0, 40), max(1.0, s / 64)))
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(body, radius, radius)

    small = size <= 24
    rows = (0.29, 0.50, 0.71)
    dot_x = s * 0.28
    text_x = s * 0.41
    for y_ratio, color in zip(rows, ROW_COLORS, strict=False):
        y = s * y_ratio
        c = QColor(color)
        if small:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(dot_x, y), s * 0.085, s * 0.085)
        else:
            # anello colorato con pallino pieno al centro, come su iOS
            p.setPen(QPen(c, s * 0.018))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(dot_x, y), s * 0.062, s * 0.062)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(dot_x, y), s * 0.040, s * 0.040)
        pen = QPen(QColor("#C7C7CC"), max(1.2, s * (0.05 if small else 0.028)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(text_x, y), QPointF(s * 0.76, y))
        if not small and y_ratio != rows[-1]:
            p.setPen(QPen(QColor("#E5E5EA"), max(1.0, s * 0.007)))
            sep_y = y + s * 0.105
            p.drawLine(QPointF(text_x - s * 0.01, sep_y), QPointF(s * 0.97 - margin, sep_y))
    p.end()
    return img


def logo_icon() -> QIcon:
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(QPixmap.fromImage(render_logo(size)))
    return icon


def write_ico(path: Path = ICO_PATH) -> Path:
    """Salva un file .ico multi-risoluzione (serve per i collegamenti di Windows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    images = [render_logo(size) for size in (16, 24, 32, 48, 64, 128, 256)]
    _save_multi_ico(images, path)
    return path


def _save_multi_ico(images: list[QImage], path: Path) -> None:
    """Formato ICO con immagini PNG incorporate (supportato da Windows Vista in poi)."""
    import struct

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    blobs = []
    for img in images:
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        buf.close()
        blobs.append((img.width(), bytes(data.data())))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, payload = b"", b""
    for size, blob in blobs:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        payload += blob
        offset += len(blob)
    path.write_bytes(header + entries + payload)
