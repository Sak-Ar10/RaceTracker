#!/usr/bin/env python3
"""
Automated Verification Test for Race Stopwatch & Leaderboard
"""

import os
import sys
import tempfile
import time
from main import DatabaseManager, RaceTrackerFrame

def test_database():
    print("--- Testing DatabaseManager ---")
    test_db = "test_race_data.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    db = DatabaseManager(test_db)
    
    # 1. User Registration
    ok, msg = db.register_user("SpeedDemon", "fastpass123")
    assert ok, f"User registration failed: {msg}"
    print("✓ Registration succeeded")

    # Duplicate username check
    ok_dup, msg_dup = db.register_user("speeddemon", "differentpass")
    assert not ok_dup, "Duplicate username check failed"
    print("✓ Duplicate username correctly rejected")

    # 2. Authentication
    auth_ok, user_data, msg_auth = db.authenticate_user("SpeedDemon", "fastpass123")
    assert auth_ok and user_data is not None, f"Authentication failed: {msg_auth}"
    assert user_data["username"] == "SpeedDemon"
    print(f"✓ Authenticated user: {user_data}")

    auth_bad, _, _ = db.authenticate_user("SpeedDemon", "wrongpassword")
    assert not auth_bad, "Bad password was incorrectly accepted"
    print("✓ Invalid password correctly rejected")

    # Register second user
    db.register_user("RacerX", "secret456")
    _, user2, _ = db.authenticate_user("RacerX", "secret456")

    # 3. Save Race Sessions with Laps
    # SpeedDemon Running: 75.50s (1m 15.5s)
    laps1 = [
        {"lap_number": 1, "lap_seconds": 37.25, "lap_time": "00:00:37.25", "total_time": "00:00:37.25"},
        {"lap_number": 2, "lap_seconds": 38.25, "lap_time": "00:00:38.25", "total_time": "00:01:15.50"}
    ]
    s_ok, s_id1, _ = db.save_race_session(user_data["user_id"], "Running", 75.50, "00:01:15.50", laps1)
    assert s_ok and s_id1 is not None, "Failed to save session 1"

    # RacerX Running: 70.10s (Faster than SpeedDemon!)
    laps2 = [
        {"lap_number": 1, "lap_seconds": 35.00, "lap_time": "00:00:35.00", "total_time": "00:00:35.00"},
        {"lap_number": 2, "lap_seconds": 35.10, "lap_time": "00:00:35.10", "total_time": "00:01:10.10"}
    ]
    s_ok2, s_id2, _ = db.save_race_session(user2["user_id"], "Running", 70.10, "00:01:10.10", laps2)
    assert s_ok2, "Failed to save session 2"

    # SpeedDemon Car: 45.20s
    laps3 = [
        {"lap_number": 1, "lap_seconds": 45.20, "lap_time": "00:00:45.20", "total_time": "00:00:45.20"}
    ]
    db.save_race_session(user_data["user_id"], "Car", 45.20, "00:00:45.20", laps3)

    # 4. Leaderboard Ranking Verification
    # Overall: Car (45.20s) -> Running RacerX (70.10s) -> Running SpeedDemon (75.50s)
    lb_all = db.get_leaderboard("All")
    assert len(lb_all) == 3, f"Expected 3 entries, got {len(lb_all)}"
    assert lb_all[0]["username"] == "SpeedDemon" and lb_all[0]["race_type"] == "Car"
    assert lb_all[1]["username"] == "RacerX" and lb_all[1]["race_type"] == "Running"
    assert lb_all[2]["username"] == "SpeedDemon" and lb_all[2]["race_type"] == "Running"
    print("✓ Global leaderboard correctly ranks entries by fastest time ascending")

    # Filtered Leaderboard (Running only): RacerX (Rank 1), SpeedDemon (Rank 2)
    lb_running = db.get_leaderboard("Running")
    assert len(lb_running) == 2, f"Expected 2 running entries, got {len(lb_running)}"
    assert lb_running[0]["rank"] == 1 and lb_running[0]["username"] == "RacerX"
    assert lb_running[1]["rank"] == 2 and lb_running[1]["username"] == "SpeedDemon"
    print("✓ Category filter correctly isolates sport and preserves rank order")

    # 5. User History Verification
    history = db.get_user_history(user_data["user_id"])
    assert len(history) == 2, f"Expected 2 sessions for SpeedDemon, got {len(history)}"
    print(f"✓ User history retrieved {len(history)} sessions")

    # 6. Session Lap Breakdown Verification
    session_laps = db.get_session_laps(s_id1)
    assert len(session_laps) == 2, f"Expected 2 laps, got {len(session_laps)}"
    assert session_laps[0]["lap_number"] == 1 and session_laps[0]["lap_time"] == "00:00:37.25"
    assert session_laps[1]["lap_number"] == 2 and session_laps[1]["lap_time"] == "00:00:38.25"
    print("✓ Session lap details verified accurately")

    # Cleanup test db
    if os.path.exists(test_db):
        os.remove(test_db)
    print("--- Database Layer Tests PASSED ---")


def test_timer_formatting():
    print("--- Testing Timer Formatting ---")
    assert RaceTrackerFrame.format_time(0.0) == "00:00:00.00"
    assert RaceTrackerFrame.format_time(59.99) == "00:00:59.99"
    assert RaceTrackerFrame.format_time(60.00) == "00:01:00.00"
    assert RaceTrackerFrame.format_time(3661.05) == "01:01:01.05"
    print("✓ Stopwatch format string conversions verified accurately")


def test_ui_headless():
    print("--- Testing UI Components & Life Cycle ---")
    import tkinter as tk
    from main import Application

    # Ensure DISPLAY is handled or catch if running in headless server
    try:
        app = Application()
    except tk.TclError as e:
        print(f"Skipping graphical UI test (no display server): {e}")
        return

    # 1. Verify initial state (Logged out)
    assert app.current_user is None
    assert app.auth_frame.winfo_viewable() or app.auth_frame.winfo_manager() == "pack"
    assert app.notebook.winfo_manager() == ""  # Hidden

    # 2. Simulate Login
    test_user = {"user_id": 999, "username": "TestDriver"}
    app.on_login_success(test_user)
    app.update_idletasks()

    assert app.current_user == test_user
    assert app.notebook.winfo_manager() == "pack"
    assert app.auth_frame.winfo_manager() == ""

    # 3. Simulate Stopwatch Interaction
    tracker = app.tracker_tab
    tracker.start_timer()
    assert tracker.is_running
    time.sleep(0.05)
    tracker.record_lap()
    assert len(tracker.laps_data) == 1
    time.sleep(0.05)
    tracker.stop_timer()
    assert not tracker.is_running

    # 4. Simulate Logout
    app.current_user = None
    app.user_info_frame.pack_forget()
    app.notebook.pack_forget()
    app.auth_frame.reset_fields()
    app.auth_frame.pack(fill="both", expand=True)
    app.update_idletasks()

    assert app.notebook.winfo_manager() == ""
    assert app.auth_frame.winfo_manager() == "pack"

    app.destroy()
    print("--- UI Life Cycle Tests PASSED ---")

if __name__ == "__main__":
    test_database()
    test_timer_formatting()
    test_ui_headless()
    print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
