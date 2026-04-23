"""Game state management using python-chess."""
import chess
from enum import Enum, auto
from PySide6.QtCore import QObject, Signal


class GameState(Enum):
    IDLE = "idle"
    PLAYER_TURN = "player_turn"
    ENGINE_THINKING = "engine_thinking"
    GAME_OVER = "game_over"


PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


class Game(QObject):
    board_updated = Signal()
    state_changed = Signal(str)   # GameState.value
    engine_move_requested = Signal(str)  # FEN string for engine thread
    game_over_signal = Signal(str)       # result message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = chess.Board()
        self.state = GameState.IDLE
        self.player_color = chess.WHITE
        self.selected_square: int | None = None
        self.last_move: chess.Move | None = None
        self.captured_by_player: list[chess.Piece] = []
        self.captured_by_engine: list[chess.Piece] = []

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def new_game(self, player_color: chess.Color = chess.WHITE):
        self.board = chess.Board()
        self.player_color = player_color
        self.selected_square = None
        self.last_move = None
        self.captured_by_player = []
        self.captured_by_engine = []

        if player_color == chess.WHITE:
            self.state = GameState.PLAYER_TURN
        else:
            self.state = GameState.ENGINE_THINKING

        self.board_updated.emit()
        self.state_changed.emit(self.state.value)

        if self.state == GameState.ENGINE_THINKING:
            self.engine_move_requested.emit(self.board.fen())

    def is_player_turn(self) -> bool:
        return (
            self.board.turn == self.player_color
            and self.state == GameState.PLAYER_TURN
        )

    def valid_targets(self, square: int) -> list[int]:
        """Return legal destination squares for the piece on `square`."""
        return [
            m.to_square
            for m in self.board.legal_moves
            if m.from_square == square
        ]

    def handle_click(self, square: int) -> bool:
        """
        Handle a player click on `square`.
        Returns True if a move was made (engine turn should follow).
        """
        if not self.is_player_turn():
            return False

        piece = self.board.piece_at(square)

        # Clicking own piece → select it
        if piece and piece.color == self.player_color:
            self.selected_square = square
            self.board_updated.emit()
            return False

        # Clicking a valid target → make the move
        if self.selected_square is not None:
            move = self._build_move(self.selected_square, square)
            if move and move in self.board.legal_moves:
                self._apply_move(move, player=True)
                self.selected_square = None
                return True

        # Clicking empty/enemy without selection → deselect
        self.selected_square = None
        self.board_updated.emit()
        return False

    def apply_engine_move(self, uci: str):
        """Called from the main thread when the engine has replied."""
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return
        if move in self.board.legal_moves:
            self._apply_move(move, player=False)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _build_move(self, from_sq: int, to_sq: int) -> chess.Move | None:
        """Build a Move, auto-promoting pawns to queen."""
        piece = self.board.piece_at(from_sq)
        promotion = None
        if piece and piece.piece_type == chess.PAWN:
            rank = chess.square_rank(to_sq)
            if (piece.color == chess.WHITE and rank == 7) or \
               (piece.color == chess.BLACK and rank == 0):
                promotion = chess.QUEEN
        return chess.Move(from_sq, to_sq, promotion=promotion)

    def _apply_move(self, move: chess.Move, player: bool):
        captured = self.board.piece_at(move.to_square)
        if captured:
            if player:
                self.captured_by_player.append(captured)
            else:
                self.captured_by_engine.append(captured)

        self.last_move = move
        self.board.push(move)
        self.board_updated.emit()

        # Check end of game
        if self.board.is_game_over():
            result = self.board.result()
            if result == "1-0":
                msg = "You win! White wins." if self.player_color == chess.WHITE else "Engine wins."
            elif result == "0-1":
                msg = "You win! Black wins." if self.player_color == chess.BLACK else "Engine wins."
            else:
                msg = "Draw!"
            self.state = GameState.GAME_OVER
            self.state_changed.emit(self.state.value)
            self.game_over_signal.emit(msg)
            return

        if player:
            self.state = GameState.ENGINE_THINKING
            self.state_changed.emit(self.state.value)
            self.engine_move_requested.emit(self.board.fen())
        else:
            self.state = GameState.PLAYER_TURN
            self.state_changed.emit(self.state.value)

    # ------------------------------------------------------------------ #
    #  Scoring helper                                                      #
    # ------------------------------------------------------------------ #

    def material_score(self) -> int:
        """Positive = player ahead, negative = engine ahead."""
        player_val = sum(PIECE_VALUES[p.piece_type] for p in self.captured_by_player)
        engine_val = sum(PIECE_VALUES[p.piece_type] for p in self.captured_by_engine)
        return player_val - engine_val
