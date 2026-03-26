"""
CycleArchive – Persistent storage of Tier-1 agent results per cycle.

After each cycle, all raw agent results are serialized to JSON in
``data/cycle_archive/{conflict}/{cycle_id}.json``. This enables:
- Replay: re-run Tier 2-5 with different prompts/weights on cached data
- Debugging: inspect raw agent outputs from past cycles
- Prompt optimization: A/B test CEO prompts on the same dataset
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dag_scheduler import ResultStore

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_DIR = os.getenv("CYCLE_ARCHIVE_DIR", "data/cycle_archive")
DEFAULT_MAX_ARCHIVES = int(os.getenv("CYCLE_ARCHIVE_MAX", "28"))  # ~7 days at 6h cycles

TIER1_AGENT_NAMES = [
    "sigint",
    "geoint",
    "satintel",
    "proximity",
    "chokepoint",
    "finint",
    "energy",
    "news",
    "socmint",
    "narrative",
    "diplo",
    "protest",
    "techint",
    "cyber",
    "acled_refs",
]


class CycleArchive:
    """Manages the persistent cycle archive."""

    def __init__(self, base_dir: str = DEFAULT_ARCHIVE_DIR, max_archives: int = DEFAULT_MAX_ARCHIVES):
        self._base_dir = Path(base_dir)
        self._max_archives = max_archives

    def save(self, store: ResultStore) -> Optional[str]:
        """Save Tier-1 agent results from a completed cycle.

        Returns the file path of the archive, or None on failure.
        """
        conflict = store.conflict or "unknown"
        cycle_id = store.cycle_id or str(int(time.time()))

        conflict_dir = self._base_dir / _safe_dirname(conflict)
        conflict_dir.mkdir(parents=True, exist_ok=True)

        archive_data = {
            "cycle_id": cycle_id,
            "conflict": conflict,
            "timestamp": time.time(),
            "agent_results": {},
        }

        for agent_name in TIER1_AGENT_NAMES:
            result = store.get(agent_name)
            if result is None:
                continue
            try:
                if hasattr(result, "model_dump"):
                    archive_data["agent_results"][agent_name] = result.model_dump(mode="json")
                elif isinstance(result, (dict, list)):
                    archive_data["agent_results"][agent_name] = result
                else:
                    archive_data["agent_results"][agent_name] = str(result)
            except Exception as e:
                logger.debug("Failed to serialize %s for archive: %s", agent_name, e)

        filepath = conflict_dir / f"{cycle_id}.json"
        try:
            filepath.write_text(json.dumps(archive_data, default=str, indent=2))
            logger.info("Cycle archived: %s", filepath)
            self._rotate(conflict_dir)
            return str(filepath)
        except Exception as e:
            logger.warning("Failed to write cycle archive: %s", e)
            return None

    def load(self, conflict: str, cycle_id: str) -> Optional[Dict[str, Any]]:
        """Load a previously archived cycle."""
        conflict_dir = self._base_dir / _safe_dirname(conflict)
        filepath = conflict_dir / f"{cycle_id}.json"
        if not filepath.exists():
            return None
        try:
            return json.loads(filepath.read_text())
        except Exception as e:
            logger.warning("Failed to load cycle archive %s: %s", filepath, e)
            return None

    def list_cycles(self, conflict: str) -> List[str]:
        """List available cycle IDs for a conflict."""
        conflict_dir = self._base_dir / _safe_dirname(conflict)
        if not conflict_dir.exists():
            return []
        return sorted(
            [f.stem for f in conflict_dir.glob("*.json")],
            reverse=True,
        )

    def load_into_store(self, conflict: str, cycle_id: str) -> Optional[ResultStore]:
        """Load archived results into a new ResultStore for replay."""
        data = self.load(conflict, cycle_id)
        if data is None:
            return None
        store = ResultStore(cycle_id=cycle_id, conflict=conflict)
        for agent_name, result in data.get("agent_results", {}).items():
            store.set(agent_name, result)
        return store

    def _rotate(self, conflict_dir: Path) -> None:
        """Remove oldest archives if we exceed the maximum."""
        archives = sorted(conflict_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
        while len(archives) > self._max_archives:
            oldest = archives.pop(0)
            try:
                oldest.unlink()
                logger.debug("Rotated old archive: %s", oldest)
            except OSError as exc:
                logger.debug("Failed to rotate archive %s: %s", oldest, exc)


def _safe_dirname(name: str) -> str:
    """Sanitize a conflict name for use as a directory name."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
