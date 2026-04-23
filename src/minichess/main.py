"""Entry point: bootstraps Qt app, handles first-run setup, wires everything together."""
import sys
import threading
import chess

from PySide6.QtWidgets import (
    QApplication, QMessageBox, QProgressDialog,
)
from PySide6.QtCore import Qt, QTimer

from .config import Config
from .game import Game
from .engine import EngineController, find_stockfish, download_stockfish
from .setup_assets import pieces_ready, download_pieces
from .tray import TrayIcon, TrayBridge
from .ui.board_window import BoardWindow


# ------------------------------------------------------------------ #
#  First-run helpers (run before Qt event loop starts)                 #
# ------------------------------------------------------------------ #

def _ensure_stockfish(config: Config, app: QApplication) -> str | None:
    """Return path to stockfish exe, downloading if needed. None = cancelled."""
    # Check config path first
    if config.stockfish_path:
        from pathlib import Path
        if Path(config.stockfish_path).exists():
            return config.stockfish_path

    # Search default dir
    exe = find_stockfish(config.stockfish_dir)
    if exe:
        config.stockfish_path = str(exe)
        config.save()
        return str(exe)

    # Ask user
    ans = QMessageBox.question(
        None,
        "Stockfish not found",
        "Stockfish chess engine is required.\n\nDownload it now? (~50 MB)",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if ans != QMessageBox.StandardButton.Yes:
        return None

    # Download with progress dialog
    dlg = QProgressDialog("Downloading Stockfish…", "Cancel", 0, 100)
    dlg.setWindowTitle("Mini Chess — Setup")
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setValue(0)
    dlg.show()
    app.processEvents()

    error_box: list[str] = []
    result: list[str] = []

    def progress_cb(msg: str, pct: int):
        dlg.setLabelText(msg)
        dlg.setValue(pct)
        app.processEvents()

    def do_download():
        try:
            exe = download_stockfish(config.stockfish_dir, progress_cb)
            result.append(str(exe))
        except Exception as e:
            error_box.append(str(e))

    t = threading.Thread(target=do_download, daemon=True)
    t.start()
    while t.is_alive():
        app.processEvents()
        t.join(timeout=0.05)
        if dlg.wasCanceled():
            return None

    dlg.close()

    if error_box:
        QMessageBox.critical(None, "Download failed", error_box[0])
        return None

    exe_path = result[0]
    config.stockfish_path = exe_path
    config.save()
    return exe_path


def _ensure_pieces(config: Config, app: QApplication) -> bool:
    """Download piece SVGs if missing. Returns True on success."""
    if pieces_ready(config.pieces_dir):
        return True

    dlg = QProgressDialog("Downloading chess pieces…", None, 0, 100)
    dlg.setWindowTitle("Mini Chess — Setup")
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setValue(0)
    dlg.show()
    app.processEvents()

    error_box: list[str] = []

    def progress_cb(msg: str, pct: int):
        dlg.setLabelText(msg)
        dlg.setValue(pct)
        app.processEvents()

    def do_download():
        try:
            download_pieces(config.pieces_dir, progress_cb)
        except Exception as e:
            error_box.append(str(e))

    t = threading.Thread(target=do_download, daemon=True)
    t.start()
    while t.is_alive():
        app.processEvents()
        t.join(timeout=0.05)

    dlg.close()

    if error_box:
        QMessageBox.warning(
            None, "Piece download failed",
            f"{error_box[0]}\n\nThe app will still run but pieces may be missing.",
        )
    return not error_box


# ------------------------------------------------------------------ #
#  Main                                                                #
# ------------------------------------------------------------------ #

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Mini Chess")

    config = Config()

    # ── First-run setup ──────────────────────────────────────────────
    stockfish_path = _ensure_stockfish(config, app)
    if not stockfish_path:
        sys.exit(0)

    _ensure_pieces(config, app)

    # ── Core objects ─────────────────────────────────────────────────
    game   = Game()
    engine = EngineController(stockfish_path, elo=config.bot_elo)

    # Wire game → engine (with artificial delay for "thinking" feel)
    def request_bot_move(fen):
        # 1.2s delay so it doesn't move instantly
        QTimer.singleShot(1200, lambda: engine.request_move(fen))

    game.engine_move_requested.connect(request_bot_move)
    engine.move_ready.connect(game.apply_engine_move)
    engine.error.connect(lambda msg: print(f"[Engine error] {msg}"))

    # ── UI ───────────────────────────────────────────────────────────
    window = BoardWindow(game, config)
    window.show()

    # ── System tray ──────────────────────────────────────────────────
    bridge = TrayBridge()
    tray   = TrayIcon(bridge, config)

    def on_show_hide():
        window.toggle_visibility()

    def on_new_game(elo: int):
        config.bot_elo = elo
        config.save()
        engine.set_elo(elo)
        side = chess.WHITE if config.player_color == "white" else chess.BLACK
        game.new_game(side)
        window.show()
        window.raise_()

    def on_quit():
        engine.shutdown()
        config.save()
        app.quit()

    bridge.show_hide_requested.connect(on_show_hide)
    bridge.new_game_requested.connect(on_new_game)
    bridge.side_changed.connect(window.handle_side_change)
    bridge.size_changed.connect(window.handle_size_change)
    bridge.quit_requested.connect(on_quit)

    # Start tray in background thread
    tray_thread = threading.Thread(target=tray.run, daemon=True)
    tray_thread.start()

    # Start first game
    game.new_game(chess.WHITE)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
