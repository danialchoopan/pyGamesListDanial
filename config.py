"""Global configuration for the Game Hub application.

All games and the hub menu import their settings from here so that
screen size, colors, audio levels and frame rates stay consistent.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
HIGHSCORES_DB: Path = DATA_DIR / "highscores.db"
SETTINGS_FILE: Path = DATA_DIR / "settings.json"

# --------------------------------------------------------------------------
# Screen / timing
# --------------------------------------------------------------------------
SCREEN_WIDTH: int = 1024
SCREEN_HEIGHT: int = 768
SCREEN_TITLE: str = "Python Game Hub"
FPS: int = 60

# Target frame rates per game. Slow/turn-based games (Snake, Tic-Tac-Toe)
# run at a low FPS on purpose: their logic advances one step per frame, so a
# low FPS literally slows the game down. Real-time games use the full 60.
DEFAULT_FPS: int = FPS
SNAKE_FPS: int = 10  # one grid step per tick -> lower FPS = calmer snake
TICTACTOE_FPS: int = 30
MEMORY_FPS: int = 60
PLATFORMER_FPS: int = 60
SPACE_SHOOTER_FPS: int = 60
BREAKOUT_FPS: int = 60

# --------------------------------------------------------------------------
# Colors (R, G, B)
# --------------------------------------------------------------------------
# Type alias so every color in the codebase reads as an RGB triple. A named
# alias documents intent and lets type-checkers catch shape mismatches.
Color = tuple[int, int, int]

BLACK: Color = (0, 0, 0)
WHITE: Color = (255, 255, 255)
GREY: Color = (128, 128, 128)
DARK_GREY: Color = (40, 40, 40)
LIGHT_GREY: Color = (200, 200, 200)

RED: Color = (220, 50, 50)
GREEN: Color = (50, 205, 50)
BLUE: Color = (30, 144, 255)
YELLOW: Color = (255, 215, 0)
ORANGE: Color = (255, 140, 0)
PURPLE: Color = (147, 112, 219)
PINK: Color = (255, 105, 180)
CYAN: Color = (0, 255, 255)
MAGENTA: Color = (255, 0, 255)

BACKGROUND: Color = (18, 18, 30)
PANEL_BG: Color = (30, 30, 48)
ACCENT: Color = (255, 215, 0)
HOVER: Color = (70, 70, 110)

# Game-specific palettes
SNAKE_BODY: Color = (50, 205, 50)
SNAKE_HEAD: Color = (34, 139, 34)
SNAKE_FOOD: Color = (220, 50, 50)
SNAKE_BG: Color = (20, 20, 20)
SNAKE_GRID: Color = (35, 35, 35)

MEMORY_CARD_BACK: Color = (51, 102, 204)
MEMORY_CARD_FRONT: Color = (240, 240, 240)
MEMORY_MATCHED: Color = (180, 240, 180)

PLATFORMER_SKY: Color = (107, 140, 255)
PLATFORMER_GROUND: Color = (139, 90, 43)
PLATFORMER_GRASS: Color = (34, 139, 34)
ENEMY_COLOR: Color = (139, 69, 19)
COIN_COLOR: Color = (255, 215, 0)

SPACE_BG: Color = (5, 5, 15)
PLAYER_SHIP: Color = (80, 200, 120)
ENEMY_SHIP: Color = (220, 60, 60)
BULLET_COLOR: Color = (255, 255, 120)
ENEMY_BULLET_COLOR: Color = (255, 120, 120)

BREAKOUT_BG: Color = (15, 15, 25)
PADDLE_COLOR: Color = (65, 105, 225)
BALL_COLOR: Color = (255, 255, 255)
BRICK_COLORS: tuple[Color, ...] = (
    (255, 99, 71),
    (255, 165, 0),
    (255, 215, 0),
    (60, 179, 113),
    (100, 149, 237),
)

# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------
# These are only *defaults*. The user's live values live in utils.Settings and
# are persisted to data/settings.json. pygame expects volumes in 0.0 - 1.0.
DEFAULT_MUSIC_VOLUME: float = 0.5  # 0.0 - 1.0
DEFAULT_SFX_VOLUME: float = 0.7  # 0.0 - 1.0
MIN_VOLUME: float = 0.0
MAX_VOLUME: float = 1.0

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
FONT_NAME: str | None = None  # None -> pygame default font
FONT_SIZE_SMALL: int = 18
FONT_SIZE_MEDIUM: int = 28
FONT_SIZE_LARGE: int = 48
FONT_SIZE_TITLE: int = 64

# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------
MENU_ITEM_SPACING: int = 70
MENU_START_Y: int = 220

# --------------------------------------------------------------------------
# Game rules / tuning
# --------------------------------------------------------------------------
# Magic numbers that define how each game *plays*. Keep them here (not
# hard-coded inside the games) so the games can be rebalanced by editing one
# file without touching any logic.
# Snake
SNAKE_CELL_SIZE: int = 25   # pixel size of one grid cell
SNAKE_GRID_SIZE: int = 24   # 24x24 cells playable area

# Memory
MEMORY_COLS: int = 4
MEMORY_ROWS: int = 4
MEMORY_MATCH_SCORE: int = 100
MEMORY_MISMATCH_PENALTY: int = 10
MEMORY_TIME_BONUS_FACTOR: int = 5

# Platformer
PLATFORMER_GRAVITY: float = 0.8       # pixels/frame^2 added to vy each tick
PLATFORMER_JUMP_STRENGTH: float = -14.0  # negative = upward (screen y grows down)
PLATFORMER_MOVE_SPEED: float = 5.0
PLATFORMER_TILE_SIZE: int = 40

# Space shooter
PLAYER_SPEED: float = 6.0
PLAYER_BULLET_SPEED: float = -10.0    # negative = bullet travels up the screen
ENEMY_BULLET_SPEED: float = 5.0       # positive = bullet travels down
ENEMY_BASE_SPEED: float = 2.0
BULLET_COOLDOWN_MS: int = 250         # min ms between player shots (fire rate)
ENEMY_ROWS: int = 4
ENEMY_COLS: int = 8

# Breakout
PADDLE_WIDTH: int = 120
PADDLE_HEIGHT: int = 18
BALL_SIZE: int = 14
BALL_BASE_SPEED: float = 6.0
BALL_SPEEDUP_PER_HIT: float = 0.3
BREAKOUT_LIVES: int = 3
BREAKOUT_BRICK_ROWS: int = 5
BREAKOUT_BRICK_COLS: int = 10
BREAKOUT_BRICK_HEIGHT: int = 26
BRICK_TOP_OFFSET: int = 80
BRICK_SIDE_MARGIN: int = 40

# Tic-Tac-Toe
TTT_BOARD_CELLS: int = 3
TTT_CELL_SIZE: int = 140
TTT_WIN_SCORE: int = 100
TTT_DRAW_SCORE: int = 25

# --------------------------------------------------------------------------
# Enhanced features (power-ups, difficulty, themes, combos)
# --------------------------------------------------------------------------
# Snake: power-ups and progressive speed-up over time.
SNAKE_POWERUP_CHANCE: float = 0.30   # chance a power-up spawns when food is eaten
SNAKE_POWERUP_TTL: int = 20          # steps a dropped power-up stays on the board
SNAKE_INVINCIBILITY_STEPS: int = 25  # steps of wall/self immunity after pickup
SNAKE_SPEED_STEPS: int = 30          # steps of speed boost after pickup
SNAKE_SPEED_BONUS_FPS: int = 6       # extra FPS while speed-boosted
SNAKE_SPEEDUP_INTERVAL: int = 50     # score earned per permanent +1 FPS
SNAKE_MAX_FPS: int = 22              # ceiling for the progressive speed-up
SNAKE_POWERUP_SCORE: int = 25        # points for collecting any power-up
SNAKE_SPEED_COLOR: Color = CYAN
SNAKE_INVINCIBLE_COLOR: Color = YELLOW

# Memory: combo scoring (consecutive matches multiply points).
MEMORY_COMBO_STEP: float = 0.5       # extra multiplier added per combo chain step
MEMORY_ANIM_SPEED: float = 6.0       # card flip animation speed (progress/second)
