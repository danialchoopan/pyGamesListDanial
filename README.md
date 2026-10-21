# 🎮 Python Game Hub

A modular Pygame application that bundles **six playable games** behind a single, navigable main menu. Built with clean architecture, full type hints, a shared utilities layer, and an automated test + CI pipeline.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Pygame](https://img.shields.io/badge/pygame-2.5%2B-green)
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
├── menu.py                 # Pygame main-menu implementation
├── base_game.py            # Abstract BaseGame all games inherit from
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
│   ├── test_snake.py
│   ├── test_tictactoe.py
│   ├── test_memory.py
│   ├── test_breakout.py
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
python main.py
```

---

## 🕹️ Controls

**Menu**
- `↑` / `↓` or mouse — select a game
- `Enter` / `Space` / click — launch
- `1`–`6` — quick-launch a game by number
- `Esc` — quit

**In-game (all games)**
- `Esc` — return to the menu
- `R` — restart the current game

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
| `pygame` | Rendering, input, audio |
| `pytest`, `pytest-cov` | Testing + coverage |
| `ruff` | Linting / formatting |
| `mypy` | Static type-checking |

---

## 📝 License

MIT — feel free to use, modify, and share.
