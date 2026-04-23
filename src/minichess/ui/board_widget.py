"""Chess board widget — renders squares, pieces, and highlights."""
import chess
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QWidget
from PySide6.QtSvg import QSvgRenderer

from ..game import Game, GameState
from .styles import (
    LIGHT_SQUARE, DARK_SQUARE,
    SELECTED_COLOR, VALID_MOVE_COLOR, LAST_MOVE_COLOR, CHECK_COLOR,
    COORD_LIGHT, COORD_DARK, COORD_FONT_SIZE,
)


class BoardWidget(QWidget):
    """Renders the 8×8 chess board with pieces and interaction."""

    clicked_square = Signal(int)  # emits chess square index (0-63)

    def __init__(self, game: Game, pieces_dir: Path, cell: int = 50, parent=None):
        super().__init__(parent)
        self._game = game
        self._pieces_dir = pieces_dir
        self._cell = cell
        self._renderers: dict[str, QSvgRenderer] = {}
        self._piece_cache: dict[str, QPixmap] = {}
        self._load_pieces()

        size = cell * 8
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        game.board_updated.connect(self.update)

    def set_cell_size(self, cell: int):
        self._cell = cell
        self.invalidate_cache()
        size = cell * 8
        self.setFixedSize(size, size)
        self.update()

    # ------------------------------------------------------------------ #
    #  Piece loading                                                       #
    # ------------------------------------------------------------------ #

    def _load_pieces(self):
        names = ["wP","wR","wN","wB","wQ","wK","bP","bR","bN","bB","bQ","bK"]
        for name in names:
            svg_path = self._pieces_dir / f"{name}.svg"
            if svg_path.exists():
                self._renderers[name] = QSvgRenderer(str(svg_path))

    def _piece_key(self, piece: chess.Piece) -> str:
        color = "w" if piece.color == chess.WHITE else "b"
        symbol = chess.piece_symbol(piece.piece_type).upper()
        return f"{color}{symbol}"

    def _get_pixmap(self, key: str) -> QPixmap | None:
        if key in self._piece_cache:
            return self._piece_cache[key]
        if key not in self._renderers:
            return None
        px = QPixmap(self._cell, self._cell)
        px.fill(Qt.GlobalColor.transparent)
        painter = QPainter(px)
        self._renderers[key].render(painter)
        painter.end()
        self._piece_cache[key] = px
        return px

    def invalidate_cache(self):
        self._piece_cache.clear()

    # ------------------------------------------------------------------ #
    #  Coordinate helpers                                                  #
    # ------------------------------------------------------------------ #

    def _sq_to_rect(self, sq: int) -> QRect:
        """Convert a chess square (0-63) to a pixel QRect."""
        file = chess.square_file(sq)
        rank = chess.square_rank(sq)
        
        # If playing as Black, flip the board
        if self._game.player_color == chess.BLACK:
            col = 7 - file
            row = rank
        else:
            col = file
            row = 7 - rank
            
        return QRect(col * self._cell, row * self._cell, self._cell, self._cell)

    def _point_to_sq(self, pos: QPoint) -> int | None:
        col = pos.x() // self._cell
        row = pos.y() // self._cell
        
        if self._game.player_color == chess.BLACK:
            file = 7 - col
            rank = row
        else:
            file = col
            rank = 7 - row
            
        if 0 <= file <= 7 and 0 <= rank <= 7:
            return chess.square(file, rank)
        return None

    # ------------------------------------------------------------------ #
    #  Paint                                                               #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_squares(painter)
        self._draw_highlights(painter)
        self._draw_pieces(painter)
        self._draw_coordinates(painter)

    def _draw_squares(self, p: QPainter):
        for sq in range(64):
            rect = self._sq_to_rect(sq)
            file = chess.square_file(sq)
            rank = chess.square_rank(sq)
            color = LIGHT_SQUARE if (file + rank) % 2 == 0 else DARK_SQUARE
            p.fillRect(rect, color)

    def _draw_highlights(self, p: QPainter):
        game = self._game

        # Last move
        if game.last_move:
            for sq in (game.last_move.from_square, game.last_move.to_square):
                p.fillRect(self._sq_to_rect(sq), LAST_MOVE_COLOR)

        # King in check
        if game.board.is_check():
            king_sq = game.board.king(game.board.turn)
            if king_sq is not None:
                p.fillRect(self._sq_to_rect(king_sq), CHECK_COLOR)

        # Selected square
        if game.selected_square is not None:
            p.fillRect(self._sq_to_rect(game.selected_square), SELECTED_COLOR)

            # Valid move dots
            for target in game.valid_targets(game.selected_square):
                rect = self._sq_to_rect(target)
                occupied = game.board.piece_at(target) is not None
                if occupied:
                    # Draw corner triangles for captures
                    p.setBrush(VALID_MOVE_COLOR)
                    p.setPen(Qt.PenStyle.NoPen)
                    half = self._cell
                    p.fillRect(rect, VALID_MOVE_COLOR)
                else:
                    # Draw a circle dot in center
                    cx = rect.center().x()
                    cy = rect.center().y()
                    r  = self._cell // 6
                    p.setBrush(VALID_MOVE_COLOR)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawEllipse(QPoint(cx, cy), r, r)

    def _draw_pieces(self, p: QPainter):
        for sq in range(64):
            piece = self._game.board.piece_at(sq)
            if not piece:
                continue
            key = self._piece_key(piece)
            pixmap = self._get_pixmap(key)
            if pixmap:
                rect = self._sq_to_rect(sq)
                p.drawPixmap(rect, pixmap)

    def _draw_coordinates(self, p: QPainter):
        font = QFont("Segoe UI", COORD_FONT_SIZE, QFont.Weight.Bold)
        p.setFont(font)
        files = "abcdefgh"
        is_black = self._game.player_color == chess.BLACK

        for i in range(8):
            # Rank numbers (1-8)
            # If White: 8 at top (row 0), 1 at bottom (row 7)
            # If Black: 1 at top (row 0), 8 at bottom (row 7)
            rank_val = i + 1 if is_black else 8 - i
            row = i
            
            # Use color of square at (0, i)
            # Square (0, i) in pixel space is square(file=0 or 7, rank=8-i or i)
            sq_at_edge = self._point_to_sq(QPoint(0, row * self._cell))
            file_idx = chess.square_file(sq_at_edge)
            rank_idx = chess.square_rank(sq_at_edge)
            is_light = (file_idx + rank_idx) % 2 == 0
            color = COORD_DARK if is_light else COORD_LIGHT
            
            p.setPen(color)
            p.drawText(QRect(2, row * self._cell + 2, 14, 14), 
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, 
                       str(rank_val))

            # File letters (a-h)
            # If White: a at left (col 0), h at right (col 7)
            # If Black: h at left (col 0), a at right (col 7)
            file_char = files[7 - i] if is_black else files[i]
            col = i
            
            sq_at_bottom = self._point_to_sq(QPoint(col * self._cell, 7 * self._cell))
            file_idx2 = chess.square_file(sq_at_bottom)
            rank_idx2 = chess.square_rank(sq_at_bottom)
            is_light2 = (file_idx2 + rank_idx2) % 2 == 0
            color2 = COORD_DARK if is_light2 else COORD_LIGHT
            
            p.setPen(color2)
            p.drawText(QRect(col * self._cell + self._cell - 14, 7 * self._cell + self._cell - 16, 14, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                       file_char)

    # ------------------------------------------------------------------ #
    #  Mouse                                                               #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            sq = self._point_to_sq(event.position().toPoint())
            if sq is not None:
                self.clicked_square.emit(sq)
        super().mousePressEvent(event)
