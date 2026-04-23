"""Classic wood-style theme constants."""
from PySide6.QtGui import QColor

# Board squares
LIGHT_SQUARE  = QColor("#F0D9B5")
DARK_SQUARE   = QColor("#B58863")

# Highlights
SELECTED_COLOR    = QColor(20, 85, 30, 180)   # dark green overlay
VALID_MOVE_COLOR  = QColor(20, 85, 30, 100)   # lighter green dot
LAST_MOVE_COLOR   = QColor(205, 210, 106, 180) # yellow tint
CHECK_COLOR       = QColor(200, 50, 50, 200)   # red flash

# Window / chrome
WINDOW_BG         = QColor("#2C1A0E")           # deep dark wood
HEADER_BG         = QColor("#3D2510")
HEADER_TEXT       = QColor("#F0D9B5")
BORDER_COLOR      = QColor("#8B5E3C")

# Coordinate labels
COORD_LIGHT       = QColor("#B58863")           # on light square
COORD_DARK        = QColor("#F0D9B5")           # on dark square

# Captured panel
CAPTURED_BG       = QColor("#3D2510")
SCORE_POSITIVE    = QColor("#90EE90")           # player ahead
SCORE_NEGATIVE    = QColor("#FF6B6B")           # engine ahead
SCORE_NEUTRAL     = QColor("#F0D9B5")

# Fonts
HEADER_FONT_FAMILY = "Segoe UI"
COORD_FONT_SIZE    = 9   # pt
