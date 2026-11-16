# Race Stopwatch & Leaderboard Application

A sleek, high-precision desktop application for race timing, lap tracking, and global leaderboard ranking built with **Python**, **Tkinter**, **ttk**, and **SQLite3**.

---

## Features

- **Object-Oriented Architecture (OOP)**: Modular separation between the main `Application` controller, `DatabaseManager` persistence layer, and custom `ttk.Frame` components.
- **SQLite3 Local Database (`race_data.db`)**:
  - Relational schema with foreign keys: `Users` ➔ `RaceSessions` ➔ `Laps`.
  - Transaction-safe connection handling using context managers.
  - Secure password hashing using SHA-256 with salt.
- **Precision Stopwatch Engine**:
  - Monotonic high-resolution timing via `time.perf_counter()`.
  - Non-drifting pause/resume delta math.
  - Hundredths-of-a-second real-time display (`00:00:00.00`).
  - Real-time lap split logging.
- **Global Leaderboard**:
  - Automatically sorts fastest times ascending (`ORDER BY total_seconds ASC`).
  - Sport/Race type dropdown filter (`Running`, `Car`, `Bike`, `Swimming`, `Karting`, etc.).
  - Automatic dynamic refresh when new sessions are saved.
  - Top 3 medal badges (🥇 #1, 🥈 #2, 🥉 #3).
- **Personal Race History**:
  - Displays all past sessions for the logged-in user.
  - Interactive lap inspector: Click any session row to view the lap breakdown.
- **Modern Dark Theme**:
  - Background: `#1E1E2E`
  - Text: `#CDD6F4`
  - Accents/Buttons: `#313244` (Hover/Active: `#45475A`)
  - Timer Font: `Helvetica, 48, bold`
  - Flat, themed `ttk.Treeview` tables with alternating rows and contrast headers.

---

## How to Run

1. Make sure Python 3 is installed with Tkinter support (standard in most Python installations).
2. Launch the application:
   ```bash
   python3 main.py
   ```

---

## File Structure

```
├── main.py        # Complete, standalone executable application
├── test_app.py    # Automated test suite for Database, Timer, and State flow
└── README.md      # Documentation and usage guide
```
