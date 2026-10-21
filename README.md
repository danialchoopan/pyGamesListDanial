# 🎮 Python Game Hub

A modular Pygame application that bundles **six playable games** behind a single, navigable main menu. Built with clean architecture, full type hints, a shared utilities layer, and an automated test + CI pipeline.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Pygame-ce](https://img.shields.io/badge/pygame--ce-2.5%2B-green)
![pygame-gui](https://img.shields.io/badge/pygame--gui-0.6%2B-8A2BE2)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## ✨ The Games

| # | Game | Description |
|---|------|-------------|
| 1 | **Snake** | Eat food, grow, and avoid walls and your own tail. |
| 2 | **Tic-Tac-Toe** | Classic Xs & Os against an *unbeatable* Minimax AI. |
| 3 | **Memory Cards** | Flip and match all the pairs in as few moves as possible. |
| 4 | **Platformer** | Mario-style run, jump, stomp enemies, and reach the flag. |
| 5 | **Space Shooter** | Blast descending alien waves Galaga-style. |
| 6 | **Breakout** | Smash every brick with your paddle and ball. |

Every game tracks **high scores** in a local SQLite database.

---

## 📁 Project Structure

```
danialPyGames/
├── main.py                 # Entry point: boots pygame + main menu
├── run.py                  # CLI launcher: --list games, --game NAME to jump in
├── menu.py                 # pygame-gui main menu (list, details, live settings)
├── base_game.py            # Abstract BaseGame all games inherit from
├── ui.py                   # pygame-gui layer: hub theme + pause/game-over dialogs
├── assets.py               # Asset manager + audio service (procedural SFX/music)
├── config.py               # Global settings (screen, colors, audio, tuning)
├── utils.py                # Shared utilities: settings + SQLite high scores
├── games/
│   ├── __init__.py         # GAME_CLASSES registry (order shown in menu)
│   ├── snake.py            # Snake  (SnakeLogic + SnakeGame)
│   ├── tictactoe.py        # Tic-Tac-Toe  (Board, MinimaxAI + TicTacToeGame)
│   ├── memory.py           # Memory Cards (MemoryBoard + MemoryGame)
│   ├── platformer.py       # Platformer  (PlatformerLevel + PlatformerGame)
│   ├── space_shooter.py    # Space Shooter (WaveManager + SpaceShooterGame)
│   └── breakout.py         # Breakout  (BreakoutPhysics + BreakoutGame)
├── tests/                  # pytest suite (logic tested without a display)
│   ├── conftest.py
│   ├── test_settings.py
│   ├── test_highscores.py
│   ├── test_assets.py
│   ├── test_base_game.py
│   ├── test_snake.py
│   ├── test_tictactoe.py
│   ├── test_memory.py
│   ├── test_platformer.py
│   ├── test_space_shooter.py
│   ├── test_breakout.py
│   ├── test_run.py
│   └── test_games_registry.py
├── .github/workflows/ci.yml  # GitHub Actions: lint + typecheck + test
├── config.toml / pyproject.toml   # tool config (pytest, ruff, mypy)
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Dev/test dependencies
└── README.md
```

### Architecture

Each game separates **pure logic** from **rendering/input**:

- **Logic classes** (`SnakeLogic`, `Board`, `MinimaxAI`, `MemoryBoard`, `PlatformerLevel`, `WaveManager`, `BreakoutPhysics`) hold all game rules and are unit-tested **headlessly** (no display needed).
- **Game classes** (`SnakeGame`, …) inherit from `BaseGame`, which provides a ready-made `run()` loop plus shared HUD / game-over / scoring helpers. A game only implements `handle_events`, `update`, `draw`, and `reset`.

A thin **pygame-gui layer** (`ui.py`) gives the whole hub a consistent, themed look: the main menu (`menu.py`) is a widget-driven screen with a game list, details pane, and live volume/FPS settings, and `BaseGame` shows the same themed pause and game-over **dialogs with working buttons** (Resume / Restart / Retry / Menu). When no display is available (headless tests), these fall back to plain-text overlays so the suite never needs a window.

The menu iterates over `games.GAME_CLASSES`, so **adding a game is as simple as creating a new `BaseGame` subclass and appending it to that list.**

---

## 🚀 Installation

### Prerequisites
- **Python 3.10+** (tested up to 3.13)
- A working display for actually playing (tests run headless)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/danialPyGames.git
cd danialPyGames

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install runtime dependencies
pip install -r requirements.txt
# ...or install dev dependencies for testing/linting:
pip install -r requirements-dev.txt
```

### ▶️ Run the Game Hub

```bash
python main.py      # boot straight into the menu
```

Or use the `run.py` launcher, which can also list the games and jump
straight into one without the menu:

```bash
python run.py                 # same as main.py - boot the menu
python run.py --list          # print the games (keys + descriptions) and exit
python run.py --game snake    # launch a single game by key or name
python run.py --game Breakout # names are matched case-insensitively
```

---

## 🕹️ Controls

**Menu**
- `↑` / `↓` or mouse — select a game (click, or double-click a row, to launch)
- `Enter` / `Space` / **Play selected game** button — launch
- `1`–`6` — quick-launch a game by number
- Volume sliders — tweak music / SFX live; the change is saved for next time
- **Show FPS counter** checkbox — toggle the in-game FPS readout
- `Esc` / **Quit** button — quit

**In-game (all games)**
- `Esc` — return to the menu
- `P` — pause/resume (the pause dialog also offers Resume / Restart / Menu buttons)
- `R` — restart the current game (the game-over dialog offers Retry / Menu buttons)

Per-game keys are shown on each game's screen (arrow keys / WASD to move, `Space` to shoot/launch, mouse to click, etc.).

---

## 🧪 Testing

The suite uses **pytest** and tests all game logic without opening a window.

```bash
# Run all tests
pytest

# Run with a coverage report
pytest --cov --cov-report=term-missing
```

### Static analysis

```bash
ruff check .        # lint
mypy .              # type-check
```

---

## ⚙️ Configuration

Global settings live in [`config.py`](config.py): screen size, the color palette, audio levels, frame rates, and per-game tuning constants (gravity, speeds, brick layout, …). User preferences (music/SFX volume, fullscreen, show-FPS) are persisted to `data/settings.json`, and high scores to `data/highscores.db` (both auto-created and git-ignored).

---

## 🔧 CI / CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and pull request to `main`/`master` across Python **3.10–3.12**:

1. Install dependencies
2. `ruff check .` — lint
3. `mypy .` — type-check
4. `pytest --cov` — tests (headless via `SDL_VIDEODRIVER=dummy`)
5. Smoke-import the hub

---

## 🧩 Adding a New Game

1. Create `games/my_game.py` with a `MyGame(BaseGame)` class implementing `handle_events`, `update`, `draw`, and `reset`.
2. Give it class attributes: `name`, `description`, `score_key`, and optionally `fps`.
3. Register it in `games/__init__.py` by importing it and appending to `GAME_CLASSES`.
4. Add tests for any pure logic in `tests/`.

The menu picks it up automatically.

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `pygame-ce` | Rendering, input, audio (actively maintained community fork of `pygame`) |
| `pygame-gui` | Themed UI widgets: main menu, pause & game-over dialogs |
| `pytest`, `pytest-cov` | Testing + coverage |
| `ruff` | Linting / formatting |
| `mypy` | Static type-checking |

---

## 📝 License

MIT — feel free to use, modify, and share.
