"""System tray icon and context menu using pystray."""
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from PySide6.QtCore import QObject, Signal

from .engine import ELO_LABELS, ELO_LEVELS


def _make_tray_icon() -> Image.Image:
    """Generate a simple chess pawn icon for the system tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Dark wood background circle
    d.ellipse([2, 2, size - 2, size - 2], fill="#3D2510")

    # Simple pawn shape in light color
    cx = size // 2
    # Head
    d.ellipse([cx - 9, 8, cx + 9, 26], fill="#F0D9B5")
    # Neck
    d.rectangle([cx - 5, 24, cx + 5, 32], fill="#F0D9B5")
    # Body
    d.polygon(
        [(cx - 12, 54), (cx + 12, 54), (cx + 7, 32), (cx - 7, 32)],
        fill="#F0D9B5",
    )
    # Base
    d.rectangle([cx - 14, 50, cx + 14, 56], fill="#F0D9B5")

    return img


class TrayBridge(QObject):
    """Qt signals fired from the pystray thread → handled on the Qt main thread."""
    show_hide_requested = Signal()
    new_game_requested  = Signal(int)   # ELO
    side_changed        = Signal(str)   # "white" or "black"
    size_changed        = Signal(int)   # pixel size
    quit_requested      = Signal()


class TrayIcon:
    def __init__(self, bridge: TrayBridge, config):
        self._bridge = bridge
        self._config = config
        self._icon: pystray.Icon | None = None

    def _build_menu(self) -> pystray.Menu:
        elo_items = [
            pystray.MenuItem(
                ELO_LABELS[elo],
                self._make_elo_handler(elo),
                checked=lambda item, e=elo: self._config.bot_elo == e,
                radio=True,
            )
            for elo in ELO_LEVELS
        ]

        side_items = [
            pystray.MenuItem("White", lambda: self._on_side("white"), checked=lambda i: self._config.player_color == "white", radio=True),
            pystray.MenuItem("Black", lambda: self._on_side("black"), checked=lambda i: self._config.player_color == "black", radio=True),
        ]

        size_items = [
            pystray.MenuItem("Small (240px)",  lambda: self._on_size(240), checked=lambda i: self._config.board_size == 240, radio=True),
            pystray.MenuItem("Medium (320px)", lambda: self._on_size(320), checked=lambda i: self._config.board_size == 320, radio=True),
            pystray.MenuItem("Large (480px)",  lambda: self._on_size(480), checked=lambda i: self._config.board_size == 480, radio=True),
        ]

        return pystray.Menu(
            pystray.MenuItem("Show / Hide board", self._on_show_hide, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("New game vs bot", pystray.Menu(*elo_items)),
            pystray.MenuItem("Play as side", pystray.Menu(*side_items)),
            pystray.MenuItem("Board size", pystray.Menu(*size_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _make_elo_handler(self, elo: int):
        def handler(icon, item):
            self._config.bot_elo = elo
            self._config.save()
            self._bridge.new_game_requested.emit(elo)
        return handler

    def _on_side(self, side: str):
        self._config.player_color = side
        self._config.save()
        self._bridge.side_changed.emit(side)

    def _on_size(self, size: int):
        self._config.board_size = size
        self._config.save()
        self._bridge.size_changed.emit(size)

    def _on_show_hide(self, icon, item):
        self._bridge.show_hide_requested.emit()

    def _on_quit(self, icon, item):
        self._bridge.quit_requested.emit()
        icon.stop()

    def run(self):
        """Blocking — call from a daemon thread."""
        img = _make_tray_icon()
        self._icon = pystray.Icon(
            "minichess",
            img,
            "Mini Chess",
            menu=self._build_menu(),
        )
        self._icon.run()

    def stop(self):
        if self._icon:
            self._icon.stop()
