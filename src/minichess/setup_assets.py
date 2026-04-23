"""Download CBurnett SVG chess pieces from Lichess on first run."""
import requests
from pathlib import Path

PIECES = [
    "wP", "wR", "wN", "wB", "wQ", "wK",
    "bP", "bR", "bN", "bB", "bQ", "bK",
]

BASE_URL = (
    "https://raw.githubusercontent.com/lichess-org/lila/"
    "master/public/piece/cburnett/{name}.svg"
)


def pieces_ready(pieces_dir: Path) -> bool:
    return all((pieces_dir / f"{p}.svg").exists() for p in PIECES)


def download_pieces(pieces_dir: Path, progress_cb=None) -> None:
    pieces_dir.mkdir(parents=True, exist_ok=True)
    total = len(PIECES)
    for i, name in enumerate(PIECES):
        dest = pieces_dir / f"{name}.svg"
        if dest.exists():
            continue
        if progress_cb:
            progress_cb(f"Downloading piece {name}…", int(i / total * 100))
        url = BASE_URL.format(name=name)
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        dest.write_bytes(r.content)
    if progress_cb:
        progress_cb("Pieces ready!", 100)
