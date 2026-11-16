#!/usr/bin/env python3
"""
Race Stopwatch & Leaderboard Application
=========================================
A desktop application built using Python, standard tkinter, tkinter.ttk, and sqlite3.
Features:
  - Local SQLite3 persistence for Users, RaceSessions, and Laps.
  - Secure user authentication (password hashing with SHA-256 and salt).
  - High-precision digital stopwatch with lap recording.
  - Real-time session lap breakdown.
  - Global leaderboard with category filtering.
  - Personal race history with detailed lap inspector.
  - Sleek modern dark theme (#1E1E2E Catppuccin-inspired).

"""

import os
import sys
import time
import hashlib
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime


# ============================================================================
# 1. DATABASE LAYER
# ============================================================================

class DatabaseManager:
    """
    Manages SQLite3 local database connections and queries.
    
    Database Connection Handling Explanation:
    -----------------------------------------
    1. Per-operation connections: SQLite connections in Python should ideally be
       opened and closed per thread/transaction or scoped using context managers
       ('with sqlite3.connect(...) as conn:').
    2. Context Manager Behavior:
       - 'with sqlite3.connect(...) as conn:' automatically commits transactions
         if no exception occurs, and rolls back if an exception is raised.
       - 'PRAGMA foreign_keys = ON;' is explicitly enabled for every connection
         to enforce relational integrity between Users -> RaceSessions -> Laps.
    3. Thread-safety & Concurrency:
       - Using a local database file with short-lived connections ensures safe
         read/write access without lingering file locks.
    4. Query Parameterization:
       - All queries use parameterized SQL ('?' or ':key') to completely eliminate
         SQL injection risks and handle special characters gracefully.
    """

    def __init__(self, db_path: str = "race_data.db"):
        self.db_path = db_path
        self.initialize_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a new SQLite connection with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row  # Enables column-name access on rows
        return conn

    def initialize_db(self) -> None:
        """Creates the necessary database tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # RaceSessions Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS RaceSessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    race_type TEXT NOT NULL,
                    total_seconds REAL NOT NULL,
                    total_time TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
                );
            """)

            # Laps Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Laps (
                    lap_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    lap_number INTEGER NOT NULL,
                    lap_seconds REAL NOT NULL,
                    lap_time TEXT NOT NULL,
                    total_time TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES RaceSessions(session_id) ON DELETE CASCADE
                );
            """)

            # Indexing for fast leaderboard & history sorting
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_type_time 
                ON RaceSessions (race_type, total_seconds ASC);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user 
                ON RaceSessions (user_id, timestamp DESC);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_laps_session 
                ON Laps (session_id, lap_number ASC);
            """)

    @staticmethod
    def _hash_password(password: str, salt: str = "race_stopwatch_salt") -> str:
        """Returns a secure SHA-256 hash of the password with salt."""
        salted = f"{salt}:{password}:{salt}"
        return hashlib.sha256(salted.encode('utf-8')).hexdigest()

    def register_user(self, username: str, password: str) -> tuple[bool, str]:
        """
        Registers a new user with a hashed password.
        Returns (success: bool, message: str).
        """
        username = username.strip()
        if not username:
            return False, "Username cannot be empty."
        if len(password) < 4:
            return False, "Password must be at least 4 characters."

        pw_hash = self._hash_password(password)
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO Users (username, password_hash) VALUES (?, ?);",
                    (username, pw_hash)
                )
                return True, "Registration successful! You can now log in."
        except sqlite3.IntegrityError:
            return False, "Username already exists. Please choose another."
        except Exception as e:
            return False, f"Registration failed: {str(e)}"

    def authenticate_user(self, username: str, password: str) -> tuple[bool, dict | None, str]:
        """
        Authenticates a user against stored password hash.
        Returns (success: bool, user_dict: dict | None, message: str).
        """
        username = username.strip()
        if not username or not password:
            return False, None, "Please enter both username and password."

        pw_hash = self._hash_password(password)
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT user_id, username, password_hash FROM Users WHERE username = ?;",
                    (username,)
                )
                row = cursor.fetchone()
                if row and row["password_hash"] == pw_hash:
                    user_data = {"user_id": row["user_id"], "username": row["username"]}
                    return True, user_data, "Login successful."
                return False, None, "Invalid username or password."
        except Exception as e:
            return False, None, f"Authentication error: {str(e)}"

    def save_race_session(
        self,
        user_id: int,
        race_type: str,
        total_seconds: float,
        total_time: str,
        laps: list[dict]
    ) -> tuple[bool, int | None, str]:
        """
        Saves a completed race session and its lap breakdown in a single atomic transaction.
        laps is a list of dicts: [{'lap_number': 1, 'lap_seconds': 12.34, 'lap_time': '00:12.34', 'total_time': '00:12.34'}, ...]
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Insert session
                cursor.execute("""
                    INSERT INTO RaceSessions (user_id, race_type, total_seconds, total_time, timestamp)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'));
                """, (user_id, race_type, total_seconds, total_time))
                
                session_id = cursor.lastrowid

                # Insert associated laps
                for lap in laps:
                    cursor.execute("""
                        INSERT INTO Laps (session_id, lap_number, lap_seconds, lap_time, total_time)
                        VALUES (?, ?, ?, ?, ?);
                    """, (
                        session_id,
                        lap["lap_number"],
                        lap["lap_seconds"],
                        lap["lap_time"],
                        lap["total_time"]
                    ))
                
                return True, session_id, "Race session saved successfully!"
        except Exception as e:
            return False, None, f"Failed to save race session: {str(e)}"

    def get_leaderboard(self, race_type: str | None = None) -> list[dict]:
        """
        Retrieves top races sorted by total_seconds ascending.
        Optionally filters by race_type.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if race_type and race_type != "All":
                    query = """
                        SELECT 
                            s.session_id,
                            u.username,
                            s.race_type,
                            s.total_time,
                            s.total_seconds,
                            s.timestamp
                        FROM RaceSessions s
                        JOIN Users u ON s.user_id = u.user_id
                        WHERE s.race_type = ?
                        ORDER BY s.total_seconds ASC
                        LIMIT 50;
                    """
                    cursor.execute(query, (race_type,))
                else:
                    query = """
                        SELECT 
                            s.session_id,
                            u.username,
                            s.race_type,
                            s.total_time,
                            s.total_seconds,
                            s.timestamp
                        FROM RaceSessions s
                        JOIN Users u ON s.user_id = u.user_id
                        ORDER BY s.total_seconds ASC
                        LIMIT 50;
                    """
                    cursor.execute(query)

                rows = cursor.fetchall()
                results = []
                for idx, row in enumerate(rows, start=1):
                    results.append({
                        "rank": idx,
                        "session_id": row["session_id"],
                        "username": row["username"],
                        "race_type": row["race_type"],
                        "total_time": row["total_time"],
                        "timestamp": row["timestamp"]
                    })
                return results
        except Exception as e:
            print(f"Error fetching leaderboard: {e}", file=sys.stderr)
            return []

    def get_user_history(self, user_id: int) -> list[dict]:
        """Fetches all past race sessions for a given user, including lap count."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT 
                        s.session_id,
                        s.race_type,
                        s.total_time,
                        s.total_seconds,
                        s.timestamp,
                        COUNT(l.lap_id) AS lap_count
                    FROM RaceSessions s
                    LEFT JOIN Laps l ON s.session_id = l.session_id
                    WHERE s.user_id = ?
                    GROUP BY s.session_id
                    ORDER BY s.timestamp DESC;
                """
                cursor.execute(query, (user_id,))
                rows = cursor.fetchall()
                return [
                    {
                        "session_id": row["session_id"],
                        "race_type": row["race_type"],
                        "total_time": row["total_time"],
                        "lap_count": row["lap_count"],
                        "timestamp": row["timestamp"]
                    }
                    for row in rows
                ]
        except Exception as e:
            print(f"Error fetching user history: {e}", file=sys.stderr)
            return []

    def get_session_laps(self, session_id: int) -> list[dict]:
        """Fetches all lap breakdowns for a specific session."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT lap_number, lap_time, total_time, lap_seconds
                    FROM Laps
                    WHERE session_id = ?
                    ORDER BY lap_number ASC;
                """
                cursor.execute(query, (session_id,))
                rows = cursor.fetchall()
                return [
                    {
                        "lap_number": row["lap_number"],
                        "lap_time": row["lap_time"],
                        "total_time": row["total_time"]
                    }
                    for row in rows
                ]
        except Exception as e:
            print(f"Error fetching session laps: {e}", file=sys.stderr)
            return []


# ============================================================================
# 2. DESIGN & THEMING CONFIGURATION
# ============================================================================

class DarkTheme:
    """
    Color constants and TTK styling definitions.
    Catppuccin Mocha-inspired modern dark theme.
    """
    BG = "#1E1E2E"             # Deep base background
    SURFACE = "#181825"        # Mantle / Card surface
    SURFACE_ALT = "#252538"    # Elevated container surface
    BORDER = "#313244"         # Border tone
    TEXT_PRIMARY = "#CDD6F4"   # Bright readable text
    TEXT_MUTED = "#A6ADC8"     # Secondary subtext
    ACCENT = "#313244"         # Button base
    ACCENT_ACTIVE = "#45475A"  # Active/Hover button
    ACCENT_HOVER = "#3b3d52"
    
    # Semantic Highlights
    COLOR_START = "#A6E3A1"    # Green
    COLOR_STOP = "#F38BA8"     # Red
    COLOR_LAP = "#89B4FA"      # Blue
    COLOR_SAVE = "#FAB387"     # Peach / Gold
    COLOR_RESET = "#6C7086"    # Gray

    @classmethod
    def apply(cls, root: tk.Tk):
        """Configures ttk styles and root window properties."""
        root.configure(bg=cls.BG)
        
        style = ttk.Style()
        # Use 'clam' or 'alt' as modern foundation for custom ttk themes
        available_themes = style.theme_names()
        if "clam" in available_themes:
            style.theme_use("clam")

        # General Frames and Labels
        style.configure(".", background=cls.BG, foreground=cls.TEXT_PRIMARY)
        style.configure("TFrame", background=cls.BG)
        style.configure("Card.TFrame", background=cls.SURFACE, relief="flat")
        style.configure("TLabel", background=cls.BG, foreground=cls.TEXT_PRIMARY, font=("Helvetica", 10))
        style.configure("Card.TLabel", background=cls.SURFACE, foreground=cls.TEXT_PRIMARY)
        style.configure("Muted.TLabel", background=cls.BG, foreground=cls.TEXT_MUTED, font=("Helvetica", 9))
        style.configure("CardMuted.TLabel", background=cls.SURFACE, foreground=cls.TEXT_MUTED, font=("Helvetica", 9))

        # Buttons (Base Dark Button)
        style.configure(
            "TButton",
            background=cls.ACCENT,
            foreground=cls.TEXT_PRIMARY,
            borderwidth=0,
            focusthickness=0,
            focuscolor="none",
            padding=[12, 6],
            font=("Helvetica", 10, "bold")
        )
        style.map(
            "TButton",
            background=[("pressed", cls.ACCENT_ACTIVE), ("active", cls.ACCENT_ACTIVE)],
            foreground=[("pressed", "#FFFFFF"), ("active", "#FFFFFF")]
        )

        # Primary Action Buttons with distinctive colors
        for name, col, text_col in [
            ("Start.TButton", cls.COLOR_START, "#11111B"),
            ("Stop.TButton", cls.COLOR_STOP, "#11111B"),
            ("Lap.TButton", cls.COLOR_LAP, "#11111B"),
            ("Save.TButton", cls.COLOR_SAVE, "#11111B"),
            ("Reset.TButton", cls.COLOR_RESET, "#FFFFFF"),
        ]:
            style.configure(
                name,
                background=col,
                foreground=text_col,
                font=("Helvetica", 10, "bold"),
                padding=[12, 6],
                borderwidth=0
            )
            style.map(
                name,
                background=[("pressed", cls.ACCENT_ACTIVE), ("active", cls.TEXT_PRIMARY)],
                foreground=[("pressed", "#FFFFFF"), ("active", "#11111B")]
            )

        # Notebook (Tabs)
        style.configure("TNotebook", background=cls.BG, borderwidth=0, tabmargins=[8, 6, 8, 0])
        style.configure(
            "TNotebook.Tab",
            background=cls.ACCENT,
            foreground=cls.TEXT_MUTED,
            padding=[18, 8],
            font=("Helvetica", 10, "bold"),
            borderwidth=0
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", cls.SURFACE_ALT), ("active", cls.ACCENT_ACTIVE)],
            foreground=[("selected", cls.TEXT_PRIMARY), ("active", "#FFFFFF")]
        )

        # Entry
        style.configure(
            "TEntry",
            fieldbackground=cls.SURFACE,
            foreground=cls.TEXT_PRIMARY,
            insertcolor=cls.TEXT_PRIMARY,
            bordercolor=cls.BORDER,
            lightcolor=cls.BORDER,
            darkcolor=cls.BORDER,
            padding=6
        )

        # Combobox
        style.configure(
            "TCombobox",
            fieldbackground=cls.SURFACE,
            background=cls.ACCENT,
            foreground=cls.TEXT_PRIMARY,
            arrowcolor=cls.TEXT_PRIMARY,
            bordercolor=cls.BORDER,
            padding=5
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", cls.SURFACE)],
            foreground=[("readonly", cls.TEXT_PRIMARY)],
            selectbackground=[("readonly", cls.ACCENT_ACTIVE)],
            selectforeground=[("readonly", "#FFFFFF")]
        )

        # Treeview (Dark Tables)
        style.configure(
            "Treeview",
            background=cls.SURFACE,
            foreground=cls.TEXT_PRIMARY,
            fieldbackground=cls.SURFACE,
            bordercolor=cls.BORDER,
            borderwidth=0,
            rowheight=30,
            font=("Helvetica", 9)
        )
        style.configure(
            "Treeview.Heading",
            background=cls.ACCENT,
            foreground=cls.TEXT_PRIMARY,
            relief="flat",
            padding=[8, 8],
            font=("Helvetica", 10, "bold")
        )
        style.map(
            "Treeview.Heading",
            background=[("active", cls.ACCENT_ACTIVE)],
            foreground=[("active", "#FFFFFF")]
        )
        style.map(
            "Treeview",
            background=[("selected", cls.ACCENT_ACTIVE)],
            foreground=[("selected", "#FFFFFF")]
        )

        # Scrollbar
        style.configure(
            "Vertical.TScrollbar",
            background=cls.ACCENT,
            troughcolor=cls.BG,
            arrowcolor=cls.TEXT_PRIMARY,
            borderwidth=0
        )


# ============================================================================
# 3. AUTHENTICATION FRAME
# ============================================================================

class AuthFrame(ttk.Frame):
    """
    Login & Registration screen with tabbed toggle and status reporting.
    Displayed when no user is currently authenticated.
    """

    def __init__(self, parent, db: DatabaseManager, on_login_success):
        super().__init__(parent)
        self.db = db
        self.on_login_success = on_login_success
        self._build_ui()

    def _build_ui(self):
        # Center container
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        card = ttk.Frame(self, style="Card.TFrame", padding=30)
        card.grid(row=0, column=0)

        # App Logo / Title Banner
        title_lbl = tk.Label(
            card,
            text="🏁 RACE STOPWATCH",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 20, "bold")
        )
        title_lbl.pack(pady=(0, 4))

        subtitle_lbl = tk.Label(
            card,
            text="Precision Timing & Global Leaderboards",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_MUTED,
            font=("Helvetica", 10)
        )
        subtitle_lbl.pack(pady=(0, 20))

        # Toggle Button Bar (Login vs Register)
        toggle_frame = tk.Frame(card, bg=DarkTheme.ACCENT, padx=2, pady=2)
        toggle_frame.pack(fill="x", pady=(0, 18))

        self.mode_var = tk.StringVar(value="login")
        self.login_btn = tk.Button(
            toggle_frame,
            text="Sign In",
            bg=DarkTheme.SURFACE_ALT,
            fg=DarkTheme.TEXT_PRIMARY,
            relief="flat",
            font=("Helvetica", 9, "bold"),
            padx=16,
            pady=6,
            command=lambda: self._set_mode("login")
        )
        self.login_btn.pack(side="left", expand=True, fill="both")

        self.reg_btn = tk.Button(
            toggle_frame,
            text="Register",
            bg=DarkTheme.ACCENT,
            fg=DarkTheme.TEXT_MUTED,
            relief="flat",
            font=("Helvetica", 9, "bold"),
            padx=16,
            pady=6,
            command=lambda: self._set_mode("register")
        )
        self.reg_btn.pack(side="left", expand=True, fill="both")

        # Form Fields
        form_frame = tk.Frame(card, bg=DarkTheme.SURFACE)
        form_frame.pack(fill="x", pady=5)

        tk.Label(
            form_frame,
            text="Username",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 9, "bold"),
            anchor="w"
        ).pack(fill="x", pady=(0, 2))

        self.username_entry = ttk.Entry(form_frame, font=("Helvetica", 10))
        self.username_entry.pack(fill="x", pady=(0, 10))
        self.username_entry.focus_set()

        tk.Label(
            form_frame,
            text="Password",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 9, "bold"),
            anchor="w"
        ).pack(fill="x", pady=(0, 2))

        self.password_entry = ttk.Entry(form_frame, show="•", font=("Helvetica", 10))
        self.password_entry.pack(fill="x", pady=(0, 10))
        self.password_entry.bind("<Return>", lambda event: self._submit())

        # Feedback / Message Label
        self.feedback_var = tk.StringVar(value="")
        self.feedback_lbl = tk.Label(
            card,
            textvariable=self.feedback_var,
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.COLOR_STOP,
            font=("Helvetica", 9),
            wraplength=280
        )
        self.feedback_lbl.pack(pady=(0, 10))

        # Submit Button
        self.submit_btn = ttk.Button(
            card,
            text="Sign In",
            style="Start.TButton",
            command=self._submit
        )
        self.submit_btn.pack(fill="x", ipady=4)

    def _set_mode(self, mode: str):
        """Switches between Login and Register views."""
        self.mode_var.set(mode)
        self.feedback_var.set("")
        if mode == "login":
            self.login_btn.config(bg=DarkTheme.SURFACE_ALT, fg=DarkTheme.TEXT_PRIMARY)
            self.reg_btn.config(bg=DarkTheme.ACCENT, fg=DarkTheme.TEXT_MUTED)
            self.submit_btn.config(text="Sign In", style="Start.TButton")
        else:
            self.login_btn.config(bg=DarkTheme.ACCENT, fg=DarkTheme.TEXT_MUTED)
            self.reg_btn.config(bg=DarkTheme.SURFACE_ALT, fg=DarkTheme.TEXT_PRIMARY)
            self.submit_btn.config(text="Create Account", style="Lap.TButton")

    def _submit(self):
        """Handles submission for either Login or Registration."""
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if self.mode_var.get() == "login":
            success, user_data, msg = self.db.authenticate_user(username, password)
            if success and user_data:
                self.feedback_lbl.config(fg=DarkTheme.COLOR_START)
                self.feedback_var.set(msg)
                self.username_entry.delete(0, tk.END)
                self.password_entry.delete(0, tk.END)
                self.on_login_success(user_data)
            else:
                self.feedback_lbl.config(fg=DarkTheme.COLOR_STOP)
                self.feedback_var.set(msg)
        else:
            success, msg = self.db.register_user(username, password)
            if success:
                self.feedback_lbl.config(fg=DarkTheme.COLOR_START)
                self.feedback_var.set(msg)
                # Switch to login mode
                self._set_mode("login")
            else:
                self.feedback_lbl.config(fg=DarkTheme.COLOR_STOP)
                self.feedback_var.set(msg)

    def reset_fields(self):
        """Clears entries and errors on logout."""
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.feedback_var.set("")
        self._set_mode("login")


# ============================================================================
# 4. TAB 1: RACE TRACKER FRAME
# ============================================================================

class RaceTrackerFrame(ttk.Frame):
    """
    Stopwatch tracking screen with lap recorder and session saver.
    
    Timer Logic Explanation:
    -----------------------
    1. Precision Clock:
       - Uses 'time.perf_counter()' which is a high-resolution, monotonic clock
         unaffected by system clock adjustments.
    2. Elapsed Calculation:
       - 'current_elapsed = elapsed_before_pause + (time.perf_counter() - start_time)'
       - Pausing adds the active duration to 'elapsed_before_pause' and resets 'start_time'.
       - This guarantees zero drift between pauses and resumes.
    3. GUI Update Loop:
       - Uses 'self.after(20, self._update_timer)' to schedule UI repaints every 20ms
         (~50 frames per second). This ensures a smooth hundredths-of-a-second display
         without choking the Tkinter main event loop.
    4. Lap Calculation:
       - When a lap is triggered, 'lap_duration = total_elapsed - last_lap_elapsed'.
       - 'last_lap_elapsed' is then updated to 'total_elapsed'.
    """

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.db = app.db

        # Timer state variables
        self.is_running = False
        self.start_perf_time = 0.0
        self.elapsed_before_pause = 0.0
        self.last_lap_elapsed = 0.0
        self.laps_data: list[dict] = []
        self._timer_job = None

        self._build_ui()

    @staticmethod
    def format_time(seconds: float) -> str:
        """Formats floating point seconds into 'HH:MM:SS.hh' string."""
        if seconds < 0:
            seconds = 0.0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        hundredths = int((seconds - int(seconds)) * 100)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{hundredths:02d}"

    def _get_current_elapsed(self) -> float:
        """Calculates total accumulated elapsed seconds up to this precise moment."""
        if self.is_running:
            return self.elapsed_before_pause + (time.perf_counter() - self.start_perf_time)
        return self.elapsed_before_pause

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Top Control Bar (Race Type Selection)
        top_bar = tk.Frame(self, bg=DarkTheme.SURFACE, padx=16, pady=12)
        top_bar.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))

        tk.Label(
            top_bar,
            text="Race Type:",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 10, "bold")
        ).pack(side="left", padx=(0, 10))

        self.race_types = ["Running", "Car", "Bike", "Swimming", "Karting", "Cycling", "Other"]
        self.race_type_var = tk.StringVar(value="Running")
        self.race_type_combo = ttk.Combobox(
            top_bar,
            textvariable=self.race_type_var,
            values=self.race_types,
            state="readonly",
            width=16,
            font=("Helvetica", 10)
        )
        self.race_type_combo.pack(side="left")

        # Session status badge
        self.status_badge_var = tk.StringVar(value="READY")
        self.status_badge = tk.Label(
            top_bar,
            textvariable=self.status_badge_var,
            bg=DarkTheme.ACCENT,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 9, "bold"),
            padx=10,
            pady=3
        )
        self.status_badge.pack(side="right")

        # Timer Display Card
        timer_card = tk.Frame(self, bg=DarkTheme.SURFACE, padx=20, pady=20)
        timer_card.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))

        self.timer_label = tk.Label(
            timer_card,
            text="00:00:00.00",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 48, "bold")
        )
        self.timer_label.pack(pady=(5, 15))

        # Action Buttons Container
        btn_bar = tk.Frame(timer_card, bg=DarkTheme.SURFACE)
        btn_bar.pack()

        self.start_btn = ttk.Button(
            btn_bar,
            text="▶ Start",
            style="Start.TButton",
            command=self.start_timer
        )
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(
            btn_bar,
            text="⏸ Pause",
            style="Stop.TButton",
            state="disabled",
            command=self.stop_timer
        )
        self.stop_btn.pack(side="left", padx=5)

        self.lap_btn = ttk.Button(
            btn_bar,
            text="⏱ Record Lap",
            style="Lap.TButton",
            state="disabled",
            command=self.record_lap
        )
        self.lap_btn.pack(side="left", padx=5)

        self.reset_btn = ttk.Button(
            btn_bar,
            text="↺ Reset",
            style="Reset.TButton",
            command=self.reset_timer
        )
        self.reset_btn.pack(side="left", padx=5)

        self.save_btn = ttk.Button(
            btn_bar,
            text="💾 Save Session",
            style="Save.TButton",
            command=self.save_session
        )
        self.save_btn.pack(side="left", padx=5)

        # Laps Treeview Container
        laps_frame = tk.Frame(self, bg=DarkTheme.SURFACE, padx=12, pady=12)
        laps_frame.grid(row=2, column=0, sticky="nsew", padx=15, pady=(0, 15))
        laps_frame.rowconfigure(1, weight=1)
        laps_frame.columnconfigure(0, weight=1)

        laps_header = tk.Frame(laps_frame, bg=DarkTheme.SURFACE)
        laps_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        tk.Label(
            laps_header,
            text="Recorded Laps Breakdown",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 11, "bold")
        ).pack(side="left")

        self.lap_count_var = tk.StringVar(value="0 laps recorded")
        tk.Label(
            laps_header,
            textvariable=self.lap_count_var,
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_MUTED,
            font=("Helvetica", 9)
        ).pack(side="right")

        # Treeview for Laps
        columns = ("lap_number", "lap_time", "total_time")
        self.laps_tree = ttk.Treeview(
            laps_frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )
        self.laps_tree.heading("lap_number", text="Lap #")
        self.laps_tree.heading("lap_time", text="Lap Time")
        self.laps_tree.heading("total_time", text="Total Elapsed Time")

        self.laps_tree.column("lap_number", width=90, anchor="center")
        self.laps_tree.column("lap_time", width=180, anchor="center")
        self.laps_tree.column("total_time", width=220, anchor="center")

        # Scrollbar for laps
        scroll = ttk.Scrollbar(laps_frame, orient="vertical", command=self.laps_tree.yview)
        self.laps_tree.configure(yscrollcommand=scroll.set)

        self.laps_tree.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")

        # Zebra striping tags
        self.laps_tree.tag_configure("evenrow", background=DarkTheme.SURFACE)
        self.laps_tree.tag_configure("oddrow", background=DarkTheme.SURFACE_ALT)

    def start_timer(self):
        """Starts or resumes the precision stopwatch."""
        if not self.is_running:
            self.is_running = True
            self.start_perf_time = time.perf_counter()
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.lap_btn.config(state="normal")
            self.status_badge_var.set("RUNNING")
            self.status_badge.config(bg=DarkTheme.COLOR_START, fg="#11111B")
            self._update_timer()

    def stop_timer(self):
        """Pauses the stopwatch without resetting elapsed time."""
        if self.is_running:
            self.is_running = False
            self.elapsed_before_pause += (time.perf_counter() - self.start_perf_time)
            if self._timer_job:
                self.after_cancel(self._timer_job)
                self._timer_job = None

            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.status_badge_var.set("PAUSED")
            self.status_badge.config(bg=DarkTheme.COLOR_STOP, fg="#11111B")
            # Update display with exact final paused value
            self.timer_label.config(text=self.format_time(self.elapsed_before_pause))

    def _update_timer(self):
        """Timer tick scheduled every 20ms while running."""
        if self.is_running:
            elapsed = self._get_current_elapsed()
            self.timer_label.config(text=self.format_time(elapsed))
            self._timer_job = self.after(20, self._update_timer)

    def record_lap(self):
        """Records the current split lap and overall cumulative time."""
        current_total = self._get_current_elapsed()
        if current_total <= 0.0:
            return

        lap_number = len(self.laps_data) + 1
        lap_seconds = current_total - self.last_lap_elapsed
        self.last_lap_elapsed = current_total

        lap_info = {
            "lap_number": lap_number,
            "lap_seconds": lap_seconds,
            "lap_time": self.format_time(lap_seconds),
            "total_time": self.format_time(current_total)
        }
        self.laps_data.append(lap_info)

        # Insert at the top of treeview (latest lap on top) or end
        tag = "oddrow" if lap_number % 2 != 0 else "evenrow"
        self.laps_tree.insert(
            "",
            "end",
            values=(f"Lap {lap_number}", lap_info["lap_time"], lap_info["total_time"]),
            tags=(tag,)
        )
        self.lap_count_var.set(f"{lap_number} {'lap' if lap_number == 1 else 'laps'} recorded")

    def reset_timer(self):
        """Resets stopwatch state and clears session laps."""
        if self.is_running:
            self.stop_timer()

        if self.laps_data or self.elapsed_before_pause > 0.0:
            if not messagebox.askyesno(
                "Reset Stopwatch",
                "Are you sure you want to reset? Any unsaved lap data will be cleared."
            ):
                return

        self.is_running = False
        self.start_perf_time = 0.0
        self.elapsed_before_pause = 0.0
        self.last_lap_elapsed = 0.0
        self.laps_data.clear()

        self.timer_label.config(text="00:00:00.00")
        for item in self.laps_tree.get_children():
            self.laps_tree.delete(item)

        self.lap_count_var.set("0 laps recorded")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.lap_btn.config(state="disabled")
        self.status_badge_var.set("READY")
        self.status_badge.config(bg=DarkTheme.ACCENT, fg=DarkTheme.TEXT_PRIMARY)

    def save_session(self):
        """Persists the current race session and all recorded laps to SQLite."""
        total_seconds = self._get_current_elapsed()
        if total_seconds <= 0.01:
            messagebox.showwarning("Empty Session", "Please track a race before saving.")
            return

        # If still running, pause first
        if self.is_running:
            self.stop_timer()

        # If no laps were manually triggered, treat the whole session as Lap 1
        laps_to_save = list(self.laps_data)
        if not laps_to_save:
            laps_to_save.append({
                "lap_number": 1,
                "lap_seconds": total_seconds,
                "lap_time": self.format_time(total_seconds),
                "total_time": self.format_time(total_seconds)
            })

        user_id = self.app.current_user["user_id"]
        race_type = self.race_type_var.get()
        formatted_total = self.format_time(total_seconds)

        success, session_id, msg = self.db.save_race_session(
            user_id=user_id,
            race_type=race_type,
            total_seconds=total_seconds,
            total_time=formatted_total,
            laps=laps_to_save
        )

        if success:
            messagebox.showinfo("Saved", f"{msg}\nSession #{session_id} saved for {race_type}.")
            # Notify Leaderboard and History tabs to reload their contents
            self.app.on_race_saved()
        else:
            messagebox.showerror("Error", msg)


# ============================================================================
# 5. TAB 2: GLOBAL LEADERBOARD FRAME
# ============================================================================

class LeaderboardFrame(ttk.Frame):
    """
    Displays the top race times pulled from SQLite with category filtering.
    Dynamically updates when filters change or when new sessions are saved.
    """

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.db = app.db
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Header and Filter bar
        filter_bar = tk.Frame(self, bg=DarkTheme.SURFACE, padx=16, pady=12)
        filter_bar.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))

        tk.Label(
            filter_bar,
            text="🏆 Global Leaderboard",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 14, "bold")
        ).pack(side="left")

        # Refresh button
        refresh_btn = ttk.Button(
            filter_bar,
            text="🔄 Refresh",
            style="TButton",
            command=self.refresh_leaderboard
        )
        refresh_btn.pack(side="right", padx=(10, 0))

        # Filter combobox
        self.filter_var = tk.StringVar(value="All")
        categories = ["All", "Running", "Car", "Bike", "Swimming", "Karting", "Cycling", "Other"]
        self.filter_combo = ttk.Combobox(
            filter_bar,
            textvariable=self.filter_var,
            values=categories,
            state="readonly",
            width=14,
            font=("Helvetica", 10)
        )
        self.filter_combo.pack(side="right")
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_leaderboard())

        tk.Label(
            filter_bar,
            text="Filter Sport:",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_MUTED,
            font=("Helvetica", 10)
        ).pack(side="right", padx=(0, 6))

        # Leaderboard Table Card
        table_card = tk.Frame(self, bg=DarkTheme.SURFACE, padx=12, pady=12)
        table_card.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        table_card.rowconfigure(0, weight=1)
        table_card.columnconfigure(0, weight=1)

        columns = ("rank", "username", "race_type", "total_time", "date")
        self.tree = ttk.Treeview(
            table_card,
            columns=columns,
            show="headings",
            selectmode="browse"
        )

        self.tree.heading("rank", text="Rank")
        self.tree.heading("username", text="Racer / User")
        self.tree.heading("race_type", text="Race Type")
        self.tree.heading("total_time", text="Record Time")
        self.tree.heading("date", text="Date Recorded")

        self.tree.column("rank", width=80, anchor="center")
        self.tree.column("username", width=160, anchor="w")
        self.tree.column("race_type", width=130, anchor="center")
        self.tree.column("total_time", width=140, anchor="center")
        self.tree.column("date", width=180, anchor="center")

        scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        # Alternating row styles
        self.tree.tag_configure("evenrow", background=DarkTheme.SURFACE)
        self.tree.tag_configure("oddrow", background=DarkTheme.SURFACE_ALT)
        self.tree.tag_configure("gold", background="#332b14", foreground="#F9E2AF")
        self.tree.tag_configure("silver", background="#2b2d38", foreground="#BAC2DE")
        self.tree.tag_configure("bronze", background="#332219", foreground="#FAB387")

    def refresh_leaderboard(self):
        """Fetches leaderboard from SQLite and updates the Treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        race_type = self.filter_var.get()
        records = self.db.get_leaderboard(race_type=race_type)

        for record in records:
            rank = record["rank"]
            if rank == 1:
                rank_str = "🥇 #1"
                tag = "gold"
            elif rank == 2:
                rank_str = "🥈 #2"
                tag = "silver"
            elif rank == 3:
                rank_str = "🥉 #3"
                tag = "bronze"
            else:
                rank_str = f"#{rank}"
                tag = "oddrow" if rank % 2 != 0 else "evenrow"

            self.tree.insert(
                "",
                "end",
                values=(
                    rank_str,
                    record["username"],
                    record["race_type"],
                    record["total_time"],
                    record["timestamp"]
                ),
                tags=(tag,)
            )


# ============================================================================
# 6. TAB 3: MY HISTORY FRAME
# ============================================================================

class HistoryFrame(ttk.Frame):
    """
    Displays the logged-in user's past race sessions.
    Selecting any race dynamically displays the lap breakdown for that session.
    """

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.db = app.db
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(2, weight=2)

        # Header Bar
        header = tk.Frame(self, bg=DarkTheme.SURFACE, padx=16, pady=12)
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))

        tk.Label(
            header,
            text="📁 My Race History",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 14, "bold")
        ).pack(side="left")

        refresh_btn = ttk.Button(
            header,
            text="🔄 Refresh",
            style="TButton",
            command=self.refresh_history
        )
        refresh_btn.pack(side="right")

        # Top Table: User Sessions
        sessions_card = tk.Frame(self, bg=DarkTheme.SURFACE, padx=12, pady=12)
        sessions_card.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        sessions_card.rowconfigure(0, weight=1)
        sessions_card.columnconfigure(0, weight=1)

        columns = ("session_id", "race_type", "total_time", "lap_count", "date")
        self.sessions_tree = ttk.Treeview(
            sessions_card,
            columns=columns,
            show="headings",
            selectmode="browse"
        )

        self.sessions_tree.heading("session_id", text="Session ID")
        self.sessions_tree.heading("race_type", text="Race Type")
        self.sessions_tree.heading("total_time", text="Total Time")
        self.sessions_tree.heading("lap_count", text="Total Laps")
        self.sessions_tree.heading("date", text="Date & Time")

        self.sessions_tree.column("session_id", width=80, anchor="center")
        self.sessions_tree.column("race_type", width=140, anchor="center")
        self.sessions_tree.column("total_time", width=140, anchor="center")
        self.sessions_tree.column("lap_count", width=100, anchor="center")
        self.sessions_tree.column("date", width=200, anchor="center")

        scroll_sessions = ttk.Scrollbar(sessions_card, orient="vertical", command=self.sessions_tree.yview)
        self.sessions_tree.configure(yscrollcommand=scroll_sessions.set)

        self.sessions_tree.grid(row=0, column=0, sticky="nsew")
        scroll_sessions.grid(row=0, column=1, sticky="ns")

        self.sessions_tree.bind("<<TreeviewSelect>>", self._on_session_selected)

        # Bottom Table: Selected Session Lap Breakdown
        laps_card = tk.Frame(self, bg=DarkTheme.SURFACE, padx=12, pady=12)
        laps_card.grid(row=2, column=0, sticky="nsew", padx=15, pady=(0, 15))
        laps_card.rowconfigure(1, weight=1)
        laps_card.columnconfigure(0, weight=1)

        self.laps_header_var = tk.StringVar(value="Select a race session above to view its lap breakdown")
        tk.Label(
            laps_card,
            textvariable=self.laps_header_var,
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_MUTED,
            font=("Helvetica", 10, "italic")
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        lap_columns = ("lap_number", "lap_time", "total_time")
        self.laps_tree = ttk.Treeview(
            laps_card,
            columns=lap_columns,
            show="headings",
            selectmode="browse"
        )
        self.laps_tree.heading("lap_number", text="Lap #")
        self.laps_tree.heading("lap_time", text="Lap Duration")
        self.laps_tree.heading("total_time", text="Cumulative Time")

        self.laps_tree.column("lap_number", width=100, anchor="center")
        self.laps_tree.column("lap_time", width=180, anchor="center")
        self.laps_tree.column("total_time", width=220, anchor="center")

        scroll_laps = ttk.Scrollbar(laps_card, orient="vertical", command=self.laps_tree.yview)
        self.laps_tree.configure(yscrollcommand=scroll_laps.set)

        self.laps_tree.grid(row=1, column=0, sticky="nsew")
        scroll_laps.grid(row=1, column=1, sticky="ns")

        # Styling tags
        self.sessions_tree.tag_configure("evenrow", background=DarkTheme.SURFACE)
        self.sessions_tree.tag_configure("oddrow", background=DarkTheme.SURFACE_ALT)
        self.laps_tree.tag_configure("evenrow", background=DarkTheme.SURFACE)
        self.laps_tree.tag_configure("oddrow", background=DarkTheme.SURFACE_ALT)

    def refresh_history(self):
        """Loads all sessions for the current logged in user."""
        for item in self.sessions_tree.get_children():
            self.sessions_tree.delete(item)
        for item in self.laps_tree.get_children():
            self.laps_tree.delete(item)
        self.laps_header_var.set("Select a race session above to view its lap breakdown")

        if not self.app.current_user:
            return

        sessions = self.db.get_user_history(self.app.current_user["user_id"])
        for idx, s in enumerate(sessions):
            tag = "oddrow" if idx % 2 != 0 else "evenrow"
            self.sessions_tree.insert(
                "",
                "end",
                iid=str(s["session_id"]),
                values=(
                    f"#{s['session_id']}",
                    s["race_type"],
                    s["total_time"],
                    s["lap_count"],
                    s["timestamp"]
                ),
                tags=(tag,)
            )

    def _on_session_selected(self, event):
        """Fired when a user clicks a race session row."""
        selected_items = self.sessions_tree.selection()
        if not selected_items:
            return

        session_id_str = selected_items[0]
        try:
            session_id = int(session_id_str)
        except ValueError:
            return

        for item in self.laps_tree.get_children():
            self.laps_tree.delete(item)

        laps = self.db.get_session_laps(session_id)
        self.laps_header_var.set(f"Showing Lap Breakdown for Session #{session_id} ({len(laps)} laps)")

        for idx, lap in enumerate(laps):
            tag = "oddrow" if idx % 2 != 0 else "evenrow"
            self.laps_tree.insert(
                "",
                "end",
                values=(f"Lap {lap['lap_number']}", lap["lap_time"], lap["total_time"]),
                tags=(tag,)
            )


# ============================================================================
# 7. MAIN APPLICATION CONTROLLER
# ============================================================================

class Application(tk.Tk):
    """
    Main Application Window and State Controller.
    Manages user session, switching between Authentication and Tabs, and theme setup.
    """

    def __init__(self):
        super().__init__()

        self.title("Race Stopwatch & Leaderboard")
        self.geometry("960x720")
        self.minsize(840, 600)

        # Initialize Database Layer
        self.db = DatabaseManager("race_data.db")

        # Current Authenticated User state
        self.current_user: dict | None = None

        # Apply Global Dark Theme
        DarkTheme.apply(self)

        # Build UI Structure
        self._build_top_header()
        self._build_main_container()

        # Center window on screen
        self._center_window()

    def _center_window(self):
        """Centers the desktop window on the primary screen."""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_top_header(self):
        """Top bar displaying app branding, user profile badge, and Logout button."""
        self.header_frame = tk.Frame(self, bg=DarkTheme.SURFACE, padx=20, pady=12)
        self.header_frame.pack(side="top", fill="x")

        # Brand Title
        brand_lbl = tk.Label(
            self.header_frame,
            text="⚡ RACING CHRONO",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT_PRIMARY,
            font=("Helvetica", 12, "bold")
        )
        brand_lbl.pack(side="left")

        # User Profile & Logout section (hidden until logged in)
        self.user_info_frame = tk.Frame(self.header_frame, bg=DarkTheme.SURFACE)
        
        self.user_badge_var = tk.StringVar(value="")
        self.user_badge = tk.Label(
            self.user_info_frame,
            textvariable=self.user_badge_var,
            bg=DarkTheme.SURFACE_ALT,
            fg=DarkTheme.COLOR_START,
            font=("Helvetica", 9, "bold"),
            padx=10,
            pady=4
        )
        self.user_badge.pack(side="left", padx=(0, 10))

        self.logout_btn = ttk.Button(
            self.user_info_frame,
            text="Logout",
            style="Stop.TButton",
            command=self.logout
        )
        self.logout_btn.pack(side="left")

    def _build_main_container(self):
        """Contains the Auth view and the Notebook tabs."""
        self.content_container = tk.Frame(self, bg=DarkTheme.BG)
        self.content_container.pack(side="top", fill="both", expand=True)

        # 1. Auth View
        self.auth_frame = AuthFrame(
            self.content_container,
            db=self.db,
            on_login_success=self.on_login_success
        )
        self.auth_frame.pack(fill="both", expand=True)

        # 2. Main Tabbed Notebook (Hidden until login)
        self.notebook = ttk.Notebook(self.content_container)

        self.tracker_tab = RaceTrackerFrame(self.notebook, self)
        self.leaderboard_tab = LeaderboardFrame(self.notebook, self)
        self.history_tab = HistoryFrame(self.notebook, self)

        self.notebook.add(self.tracker_tab, text="  ⏱ Race Tracker  ")
        self.notebook.add(self.leaderboard_tab, text="  🏆 Global Leaderboard  ")
        self.notebook.add(self.history_tab, text="  📁 My History  ")

    def on_login_success(self, user_data: dict):
        """Transitions application state from Auth to Main Tabbed View."""
        self.current_user = user_data
        self.user_badge_var.set(f"👤 {user_data['username']}")
        self.user_info_frame.pack(side="right")

        # Hide Auth frame and show Notebook
        self.auth_frame.pack_forget()
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Populate Leaderboard and History tabs
        self.leaderboard_tab.refresh_leaderboard()
        self.history_tab.refresh_history()

    def logout(self):
        """Clears user session and returns to login screen."""
        if messagebox.askyesno("Confirm Logout", "Are you sure you want to log out?"):
            # Stop any running stopwatch
            if self.tracker_tab.is_running:
                self.tracker_tab.stop_timer()

            self.current_user = None
            self.user_info_frame.pack_forget()
            self.notebook.pack_forget()

            self.auth_frame.reset_fields()
            self.auth_frame.pack(fill="both", expand=True)

    def on_race_saved(self):
        """Callback to refresh data views when a new race session is saved."""
        self.leaderboard_tab.refresh_leaderboard()
        self.history_tab.refresh_history()


# ============================================================================
# 8. PROGRAM ENTRY POINT
# ============================================================================

def main():
    """Initializes and launches the Race Stopwatch & Leaderboard application."""
    app = Application()
    app.mainloop()


if __name__ == "__main__":
    main()
