"""Persistent configuration stored in ~/.minichess/config.json"""
import json
from pathlib import Path
from dataclasses import dataclass, asdict, field

CONFIG_DIR = Path.home() / ".minichess"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class Config:
    window_x: int = -1          # -1 = auto-position bottom-right
    window_y: int = -1
    bot_elo: int = 1200
    player_color: str = "white"  # "white" or "black"
    stockfish_path: str = ""
    board_size: int = 320        # made it smaller by default (320 instead of 400)

    def __post_init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(self, k):
                        setattr(self, k, v)
            except Exception:
                pass

    def save(self):
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2), encoding="utf-8"
        )

    @property
    def stockfish_dir(self) -> Path:
        return CONFIG_DIR / "stockfish"

    @property
    def pieces_dir(self) -> Path:
        return CONFIG_DIR / "pieces"

    @property
    def cell_size(self) -> int:
        return self.board_size // 8
