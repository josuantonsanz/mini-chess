"""Main floating board window: header, board, captured pieces strip."""
import chess
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QPixmap, QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy

from ..game import Game, GameState
from ..config import Config
from ..engine import ELO_LABELS, ELO_LEVELS
from .board_widget import BoardWidget
from .styles import (
    WINDOW_BG, HEADER_BG, HEADER_TEXT, BORDER_COLOR,
    CAPTURED_BG, SCORE_POSITIVE, SCORE_NEGATIVE, SCORE_NEUTRAL,
    HEADER_FONT_FAMILY,
)

PIECE_UNICODE = {
    (chess.PAWN,   chess.WHITE): "♙",
    (chess.KNIGHT, chess.WHITE): "♘",
    (chess.BISHOP, chess.WHITE): "♗",
    (chess.ROOK,   chess.WHITE): "♖",
    (chess.QUEEN,  chess.WHITE): "♕",
    (chess.KING,   chess.WHITE): "♔",
    (chess.PAWN,   chess.BLACK): "♟",
    (chess.KNIGHT, chess.BLACK): "♞",
    (chess.BISHOP, chess.BLACK): "♝",
    (chess.ROOK,   chess.BLACK): "♜",
    (chess.QUEEN,  chess.BLACK): "♛",
    (chess.KING,   chess.BLACK): "♚",
}


class BoardWindow(QWidget):
    """Frameless, always-on-top floating chess window."""

    closed = Signal()

    def __init__(self, game: Game, config: Config, parent=None):
        super().__init__(parent)
        self._game   = game
        self._config = config
        self._drag_pos: QPoint | None = None

        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._position_window()

    # ------------------------------------------------------------------ #
    #  Window setup                                                        #
    # ------------------------------------------------------------------ #

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool            # keeps it off Alt+Tab
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(f"background-color: {WINDOW_BG.name()}; border: 2px solid {BORDER_COLOR.name()};")

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(0)

        # ── Header ──
        self._header = _Header(self._game, self._config, self)
        root.addWidget(self._header)

        # ── Board ──
        cell = self._config.cell_size
        self._board_widget = BoardWidget(
            self._game,
            self._config.pieces_dir,
            cell=cell,
            parent=self,
        )
        root.addWidget(self._board_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        # ── Captured strip ──
        self._captured = _CapturedStrip(self._game, self)
        root.addWidget(self._captured)

        self.adjustSize()

    def _connect_signals(self):
        self._board_widget.clicked_square.connect(self._on_square_clicked)
        self._game.board_updated.connect(self._captured.update_display)
        self._game.state_changed.connect(self._header.update_state)
        self._game.game_over_signal.connect(self._on_game_over)

    def _position_window(self):
        if self._config.window_x >= 0 and self._config.window_y >= 0:
            self.move(self._config.window_x, self._config.window_y)
        else:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(
                screen.right()  - self.sizeHint().width()  - 16,
                screen.bottom() - self.sizeHint().height() - 48,
            )

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    # ------------------------------------------------------------------ #
    #  Slots                                                               #
    # ------------------------------------------------------------------ #

    def _on_square_clicked(self, sq: int):
        self._game.handle_click(sq)

    def _on_game_over(self, msg: str):
        self._header.set_message(msg)

    def handle_size_change(self, size: int):
        self._config.board_size = size
        self._board_widget.set_cell_size(self._config.cell_size)
        # Force the window to resize to fit the new content
        self.setFixedSize(self.sizeHint())

    def handle_side_change(self, side: str):
        color = chess.WHITE if side == "white" else chess.BLACK
        self._game.new_game(color)
        self._board_widget.update()

    # ------------------------------------------------------------------ #
    #  Drag to move window                                                 #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        # Save position
        self._config.window_x = self.x()
        self._config.window_y = self.y()
        self._config.save()
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        self._config.window_x = self.x()
        self._config.window_y = self.y()
        self._config.save()
        self.closed.emit()
        event.ignore()   # don't actually close — just hide
        self.hide()


# ------------------------------------------------------------------ #
#  Header bar                                                          #
# ------------------------------------------------------------------ #

class _Header(QWidget):
    def __init__(self, game: Game, config: Config, parent=None):
        super().__init__(parent)
        self._game   = game
        self._config = config
        self._message = ""
        self.setFixedHeight(36)
        self.setStyleSheet(f"background-color: {HEADER_BG.name()};")

    def update_state(self, state_str: str):
        self._message = ""
        self.update()

    def set_message(self, msg: str):
        self._message = msg
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.fillRect(self.rect(), HEADER_BG)

        # Title left
        font = QFont(HEADER_FONT_FAMILY, 10, QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(HEADER_TEXT)
        p.drawText(QRect(8, 0, 100, 36),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   "♟ Mini Chess")

        # State / message center
        state = self._game.state
        if self._message:
            text = self._message
        elif state == GameState.PLAYER_TURN:
            turn = "Your turn"
            text = turn
        elif state == GameState.ENGINE_THINKING:
            elo_lbl = ELO_LABELS.get(self._config.bot_elo, str(self._config.bot_elo))
            text = f"⏳ {elo_lbl} thinking…"
        elif state == GameState.GAME_OVER:
            text = "Game over"
        else:
            text = "Ready"

        font2 = QFont(HEADER_FONT_FAMILY, 9)
        p.setFont(font2)
        p.setPen(HEADER_TEXT)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)

        # Close / hide button right
        close_rect = QRect(self.width() - 28, 4, 22, 22)
        p.setPen(QColor("#8B5E3C"))
        font3 = QFont(HEADER_FONT_FAMILY, 11)
        p.setFont(font3)
        p.setPen(HEADER_TEXT)
        p.drawText(close_rect, Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            close_rect = QRect(self.width() - 28, 4, 22, 22)
            if close_rect.contains(event.position().toPoint()):
                self.window().hide()
                return
        super().mousePressEvent(event)


# ------------------------------------------------------------------ #
#  Captured pieces strip                                               #
# ------------------------------------------------------------------ #

class _CapturedStrip(QWidget):
    def __init__(self, game: Game, parent=None):
        super().__init__(parent)
        self._game = game
        self.setFixedHeight(32)
        self.setStyleSheet(f"background-color: {CAPTURED_BG.name()};")

    def update_display(self):
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), CAPTURED_BG)

        font = QFont("Segoe UI", 12)
        p.setFont(font)
        half = self.width() // 2

        # Left: pieces captured by ENGINE (player pieces lost)
        pieces_by_engine = self._game.captured_by_engine
        text_e = "".join(
            PIECE_UNICODE.get((pc.piece_type, pc.color), "?")
            for pc in sorted(pieces_by_engine, key=lambda x: x.piece_type)
        )
        p.setPen(SCORE_NEUTRAL)
        p.drawText(QRect(8, 0, half - 20, 32),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   text_e)

        # Right: pieces captured by PLAYER (enemy pieces taken)
        pieces_by_player = self._game.captured_by_player
        text_p = "".join(
            PIECE_UNICODE.get((pc.piece_type, pc.color), "?")
            for pc in reversed(sorted(pieces_by_player, key=lambda x: x.piece_type))
        )
        p.setPen(SCORE_NEUTRAL)
        p.drawText(QRect(half + 20, 0, half - 28, 32),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   text_p)

        # Score diff in center
        score = self._game.material_score()
        if score > 0:
            score_text = f"+{score}"
            p.setPen(SCORE_POSITIVE)
        elif score < 0:
            score_text = str(score)
            p.setPen(SCORE_NEGATIVE)
        else:
            score_text = "="
            p.setPen(SCORE_NEUTRAL)

        font2 = QFont(HEADER_FONT_FAMILY, 9, QFont.Weight.Bold)
        p.setFont(font2)
        p.drawText(QRect(half - 16, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, score_text)
