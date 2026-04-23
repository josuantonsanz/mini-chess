"""Stockfish wrapper: auto-download, ELO config, async move calculation."""
import io
import os
import zipfile
from pathlib import Path

import chess
import chess.engine
import requests
from PySide6.QtCore import QObject, QThread, Signal, Slot

# ------------------------------------------------------------------ #
#  ELO presets                                                         #
# ------------------------------------------------------------------ #

ELO_LEVELS = [400, 600, 800, 1000, 1200, 1500, 1800, 2000, 2200, 2500]

ELO_LABELS = {
    400:  "Beginner (400)",
    600:  "Novice (600)",
    800:  "Casual (800)",
    1000: "Intermediate (1000)",
    1200: "Club Player (1200)",
    1500: "Strong Club (1500)",
    1800: "Advanced (1800)",
    2000: "Expert (2000)",
    2200: "Candidate Master (2200)",
    2500: "Grandmaster (2500)",
}

# Skill Level 0-20 for weaker bots; UCI_Elo for stronger ones
ELO_CONFIGS = {
    400:  {"Skill Level": 0},
    600:  {"Skill Level": 3},
    800:  {"Skill Level": 5},
    1000: {"Skill Level": 7},
    1200: {"Skill Level": 9},
    1500: {"UCI_LimitStrength": True, "UCI_Elo": 1500},
    1800: {"UCI_LimitStrength": True, "UCI_Elo": 1800},
    2000: {"UCI_LimitStrength": True, "UCI_Elo": 2000},
    2200: {"UCI_LimitStrength": True, "UCI_Elo": 2200},
    2500: {"UCI_LimitStrength": True, "UCI_Elo": 2500},
}


# ------------------------------------------------------------------ #
#  Stockfish downloader                                                #
# ------------------------------------------------------------------ #

def find_stockfish(stockfish_dir: Path) -> Path | None:
    """Search for stockfish executable under stockfish_dir."""
    # Prioritize .exe on Windows
    names = ["stockfish.exe", "stockfish"] if os.name == "nt" else ["stockfish", "stockfish.exe"]
    
    for name in names:
        p = stockfish_dir / name
        if p.exists() and p.is_file():
            return p
            
    # Look deeper if not found at top level
    for p in stockfish_dir.rglob("stockfish*.exe"):
        if p.is_file():
            return p
            
    for p in stockfish_dir.rglob("stockfish*"):
        if p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def download_stockfish(stockfish_dir: Path, progress_cb=None) -> Path:
    """Download latest Stockfish Windows binary from GitHub releases."""
    stockfish_dir.mkdir(parents=True, exist_ok=True)

    if progress_cb:
        progress_cb("Fetching latest release info…", 5)

    api = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
    resp = requests.get(api, timeout=15)
    resp.raise_for_status()
    release = resp.json()

    # Pick best Windows asset (prefer avx2)
    asset = None
    for a in release.get("assets", []):
        n = a["name"].lower()
        if "windows" in n and "avx2" in n and n.endswith(".zip"):
            asset = a
            break
    if not asset:
        for a in release.get("assets", []):
            n = a["name"].lower()
            if "windows" in n and n.endswith(".zip"):
                asset = a
                break
    if not asset:
        raise RuntimeError("No Windows Stockfish binary found in latest release.")

    if progress_cb:
        progress_cb(f"Downloading {asset['name']}…", 10)

    dl = requests.get(asset["browser_download_url"], timeout=120, stream=True)
    dl.raise_for_status()
    total = int(dl.headers.get("content-length", 0))
    chunks, downloaded = [], 0
    for chunk in dl.iter_content(8192):
        chunks.append(chunk)
        downloaded += len(chunk)
        if progress_cb and total:
            pct = 10 + int(downloaded / total * 80)
            progress_cb(f"Downloading… {downloaded // 1024} KB / {total // 1024} KB", pct)

    if progress_cb:
        progress_cb("Extracting…", 92)

    with zipfile.ZipFile(io.BytesIO(b"".join(chunks))) as zf:
        zf.extractall(stockfish_dir)

    exe = find_stockfish(stockfish_dir)
    if not exe:
        raise RuntimeError("Extraction succeeded but could not locate stockfish executable.")

    if progress_cb:
        progress_cb("Stockfish ready!", 100)
    return exe


# ------------------------------------------------------------------ #
#  Engine worker (runs in QThread)                                     #
# ------------------------------------------------------------------ #

class EngineWorker(QObject):
    move_ready = Signal(str)
    error      = Signal(str)

    def __init__(self, stockfish_path: str, elo: int = 1200):
        super().__init__()
        self._path = stockfish_path
        self._elo = elo
        self._engine: chess.engine.SimpleEngine | None = None

    @Slot()
    def start_engine(self):
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(self._path)
            self._apply_config(self._elo)
        except Exception as e:
            self.error.emit(f"Engine start failed: {e}")

    @Slot()
    def stop_engine(self):
        if self._engine:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None

    @Slot(int)
    def set_elo(self, elo: int):
        self._elo = elo
        if self._engine:
            self._apply_config(elo)

    @Slot(str)
    def calculate_move(self, fen: str):
        if not self._engine:
            self.start_engine()
            if not self._engine:
                self.error.emit("Engine not running and failed to start.")
                return
        
        try:
            board = chess.Board(fen)
            
            # Adjust limit based on ELO to make low levels easier
            # ELOs < 1200 get very restricted node counts
            if self._elo <= 600:
                limit = chess.engine.Limit(nodes=200) # Extremely weak
            elif self._elo <= 1000:
                limit = chess.engine.Limit(nodes=1000)
            elif self._elo <= 1500:
                limit = chess.engine.Limit(time=0.2)
            else:
                limit = chess.engine.Limit(time=0.5)

            result = self._engine.play(board, limit)
            if result.move:
                self.move_ready.emit(result.move.uci())
        except Exception as e:
            self.error.emit(f"Calculation error: {e}")

    def _apply_config(self, elo: int):
        cfg = ELO_CONFIGS.get(elo, {"UCI_LimitStrength": True, "UCI_Elo": elo})
        try:
            self._engine.configure({"UCI_LimitStrength": False})
            self._engine.configure(cfg)
        except Exception:
            pass


# ------------------------------------------------------------------ #
#  Controller: owns the thread                                         #
# ------------------------------------------------------------------ #

class EngineController(QObject):
    move_ready = Signal(str)
    error      = Signal(str)
    
    # Internal signals for thread communication
    _do_calculate = Signal(str)
    _do_set_elo   = Signal(int)
    _do_stop      = Signal()

    def __init__(self, stockfish_path: str, elo: int = 1200, parent=None):
        super().__init__(parent)
        self._thread = QThread()
        self._worker = EngineWorker(stockfish_path, elo)
        self._worker.moveToThread(self._thread)
        
        # Connect internal signals (Qt handles the thread hop)
        self._do_calculate.connect(self._worker.calculate_move)
        self._do_set_elo.connect(self._worker.set_elo)
        self._do_stop.connect(self._worker.stop_engine)
        
        # Connect worker outputs to controller outputs
        self._worker.move_ready.connect(self.move_ready)
        self._worker.error.connect(self.error)
        
        # Startup
        self._thread.started.connect(self._worker.start_engine)
        self._thread.start()

    def request_move(self, fen: str):
        self._do_calculate.emit(fen)

    def set_elo(self, elo: int):
        self._do_set_elo.emit(elo)

    def shutdown(self):
        self._do_stop.emit()
        self._thread.quit()
        self._thread.wait(2000)
