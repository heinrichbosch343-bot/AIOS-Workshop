"""Tests for hb_team.py (the Harties Board team board and ship lock). No network."""
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hb_team as T  # noqa: E402


@pytest.fixture(autouse=True)
def team_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TEAM_DIR", tmp_path)
    monkeypatch.setattr(T, "STATE", tmp_path / "team.json")
    monkeypatch.setattr(T, "LOCK", tmp_path / "ship.lock")
    monkeypatch.setattr(T, "BOARD", tmp_path / "TEAM.md")
    return tmp_path


def run(*args):
    return T.main(list(args))


def test_join_and_note_show_on_the_board():
    assert run("join", "--as", "s-33", "--branch", "directory", "--folder", "C:/x", "--task", "pictures", "--touches", "lib/board.ts") == 0
    assert run("note", "--as", "s-33", "shipped pictures; rerun harties_geo.py") == 0
    board = T.BOARD.read_text(encoding="utf-8")
    assert "s-33" in board and "directory" in board and "rerun harties_geo.py" in board
    assert "Ship lock: free" in board and "How we work together" in board


def test_only_one_session_can_hold_the_lock(capsys):
    assert run("lock", "--as", "a", "--branch", "nearby") == 0
    assert run("lock", "--as", "b") == 1
    assert "a holds the ship lock" in capsys.readouterr().out
    assert run("unlock", "--as", "b") == 1, "someone else cannot release it"
    assert run("unlock", "--as", "a") == 0
    assert run("lock", "--as", "b") == 0


def test_may_ship_needs_the_owner_and_a_fresh_lock():
    ok, why = T.may_ship("a")
    assert not ok and "lock" in why
    run("lock", "--as", "a")
    assert T.may_ship("a") == (True, "ok")
    ok, why = T.may_ship("b")
    assert not ok and "a holds" in why
    assert not T.may_ship(None)[0]


def test_a_stale_lock_can_be_taken_over_but_a_fresh_one_cannot_be_forced():
    run("lock", "--as", "a")
    assert run("unlock", "--as", "b", "--force") == 1
    old = json.loads(T.LOCK.read_text())
    old["since"] = T.stamp(T.now() - timedelta(minutes=61))
    T.LOCK.write_text(json.dumps(old))
    assert not T.may_ship("a")[0], "a stale lock no longer lets its owner ship"
    assert run("unlock", "--as", "b", "--force") == 0
    assert run("lock", "--as", "b") == 0 and T.may_ship("b")[0]


def test_the_log_keeps_only_the_latest_notes():
    for i in range(T.LOG_KEEP + 10):
        run("note", "--as", "a", f"n{i}")
    log = json.loads(T.STATE.read_text())["log"]
    assert len(log) == T.LOG_KEEP and log[-1]["text"] == f"n{T.LOG_KEEP + 9}"
