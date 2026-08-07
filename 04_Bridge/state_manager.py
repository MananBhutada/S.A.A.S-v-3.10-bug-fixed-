"""
04_Bridge/state_manager.py
Project S.A.A.S. — Safe Bridge State Manager
=============================================
BUG FIXES:
  - Atomic reads with try/except JSON decode — never crash on empty/corrupt file
  - Atomic writes via temp file + os.rename (prevents corruption mid-write)
  - Ward key validation — rejects single-char keys (string-iteration artifact)
  - Provides a single import point for all state I/O

Usage:
    from state_manager import load_state, save_state, safe_ward_keys
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger("STATE-MANAGER")

BASE_DIR    = Path(__file__).parent.parent
BRIDGE_PATH = BASE_DIR / "04_Bridge" / "aura_master_state.json"

_DEFAULT_STATE: dict = {
    "city":  {"name": "Delhi"},
    "wards": {}
}


def load_state() -> dict:
    """
    Safely load bridge state.
    BUG FIX: json.load() on empty or corrupt file raised ValueError/JSONDecodeError
              crashing the entire alert pipeline. Now returns default state on any error.
    """
    if not BRIDGE_PATH.exists():
        return _default()

    try:
        with open(BRIDGE_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            log.warning("Bridge state file is empty — returning default state")
            return _default()
        state = json.loads(content)
        # BUG FIX: Remove corrupted single-char ward keys caused by string iteration
        state = _clean_ward_keys(state)
        return state
    except json.JSONDecodeError as exc:
        log.error("Bridge state file is corrupt (%s) — returning default state", exc)
        return _default()
    except OSError as exc:
        log.error("Cannot read bridge state file (%s) — returning default state", exc)
        return _default()


def save_state(state: dict) -> bool:
    """
    Atomically save bridge state using temp file + os.rename.
    BUG FIX: Direct json.dump() to the live file could corrupt it if two processes
              write simultaneously or if the process is killed mid-write.
    Returns True on success, False on failure.
    """
    try:
        BRIDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory, then rename (atomic on POSIX)
        fd, tmp_path = tempfile.mkstemp(
            dir=BRIDGE_PATH.parent, prefix=".state_tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            # os.replace is atomic on both POSIX and Windows (Python 3.3+)
            os.replace(tmp_path, BRIDGE_PATH)
            return True
        except Exception:
            # Clean up temp file if rename failed
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        log.error("Failed to save bridge state: %s", exc)
        return False


def _default() -> dict:
    import copy
    return copy.deepcopy(_DEFAULT_STATE)


def _clean_ward_keys(state: dict) -> dict:
    """
    BUG FIX: When the LLM returns a comma-separated string like 'Ward-1, 2'
    and it gets iterated as characters, the wards dict ends up with keys:
    'W', 'a', 'r', 'd', '-', '1', ',', ' ', '2'
    
    These single/short invalid keys corrupt the state. Remove them.
    A valid ward key is at least 3 chars and does NOT start with a number,
    comma, or space. Also clean up bare digits.
    """
    wards = state.get("wards", {})
    valid_wards = {}
    invalid_keys = []

    for key, val in wards.items():
        # Valid ward keys are like "Ward-1", "Narela", "Alipur", etc.
        # Single chars, digits, spaces, commas are artifacts
        if len(key) >= 3 and key[0].isalpha():
            valid_wards[key] = val
        else:
            invalid_keys.append(key)

    if invalid_keys:
        log.warning("Removed %d corrupted ward keys from state: %s", len(invalid_keys), invalid_keys)

    state["wards"] = valid_wards
    return state
