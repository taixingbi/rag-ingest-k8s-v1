"""State management for incremental ingestion."""

import json
import os
from typing import Dict, Optional


def _state_file_path() -> str:
    """State file path; overridable via STATE_FILE env (e.g. /data/state.json in K8s)."""
    return os.environ.get("STATE_FILE", "state.json")


def load_state() -> Dict[str, Dict[str, str]]:
    """Load ingestion state from state.json."""
    state_file = _state_file_path()
    if not os.path.exists(state_file):
        return {}

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        import sys
        print(f"Warning: could not load state from {state_file}: {e}", file=sys.stderr, flush=True)
        return {}


def save_state(state: Dict[str, Dict[str, str]]) -> None:
    """Save ingestion state to state.json."""
    state_file = _state_file_path()
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.flush()
        if hasattr(os, "fsync"):
            os.fsync(f.fileno())


def get_file_state(filepath: str, state: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Get state for a specific file."""
    return state.get(filepath)


def update_file_state(
    filepath: str,
    content_hash: str,
    mtime: str,
    state: Dict[str, Dict[str, str]],
) -> None:
    """Update state for a specific file."""
    state[filepath] = {
        "content_hash": content_hash,
        "mtime": mtime,
    }


def should_skip_file(
    filepath: str,
    current_hash: str,
    current_mtime: str,
    state: Dict[str, Dict[str, str]],
) -> bool:
    """Check if file should be skipped (unchanged since last ingest)."""
    file_state = get_file_state(filepath, state)
    if file_state is None:
        return False
    
    return (
        file_state.get("content_hash") == current_hash
        and file_state.get("mtime") == current_mtime
    )
