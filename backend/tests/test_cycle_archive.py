"""
Tests for CycleArchive: save, load, list, rotation, replay.
"""

import json
import time

import pytest

from agents.cycle_archive import CycleArchive, _safe_dirname
from agents.dag_scheduler import ResultStore


@pytest.fixture
def tmp_archive(tmp_path):
    return CycleArchive(base_dir=str(tmp_path), max_archives=3)


class TestSave:
    def test_saves_tier1_results(self, tmp_archive):
        store = ResultStore(cycle_id="c001", conflict="Iran")
        store.set("sigint", {"sigint_score": 65, "aircraft": []})
        store.set("news", {"news_score": 45, "articles": []})
        store.set("ner_extract", "should_be_excluded")

        path = tmp_archive.save(store)
        assert path is not None
        data = json.loads(open(path).read())
        assert data["cycle_id"] == "c001"
        assert data["conflict"] == "Iran"
        assert "sigint" in data["agent_results"]
        assert "news" in data["agent_results"]
        assert "ner_extract" not in data["agent_results"]

    def test_handles_empty_store(self, tmp_archive):
        store = ResultStore(cycle_id="c002", conflict="Taiwan")
        path = tmp_archive.save(store)
        assert path is not None


class TestLoad:
    def test_load_saved_archive(self, tmp_archive):
        store = ResultStore(cycle_id="c003", conflict="Iran")
        store.set("sigint", {"score": 50})
        tmp_archive.save(store)

        data = tmp_archive.load("Iran", "c003")
        assert data is not None
        assert data["agent_results"]["sigint"]["score"] == 50

    def test_load_nonexistent_returns_none(self, tmp_archive):
        assert tmp_archive.load("Iran", "nonexistent") is None


class TestListCycles:
    def test_lists_saved_cycles(self, tmp_archive):
        for cid in ["c1", "c2", "c3"]:
            store = ResultStore(cycle_id=cid, conflict="Iran")
            tmp_archive.save(store)

        cycles = tmp_archive.list_cycles("Iran")
        assert len(cycles) == 3
        assert "c1" in cycles

    def test_empty_for_unknown_conflict(self, tmp_archive):
        assert tmp_archive.list_cycles("unknown") == []


class TestRotation:
    def test_rotates_old_archives(self, tmp_archive):
        for i in range(5):
            store = ResultStore(cycle_id=f"c{i}", conflict="Iran")
            tmp_archive.save(store)
            time.sleep(0.01)

        cycles = tmp_archive.list_cycles("Iran")
        assert len(cycles) <= 3


class TestReplay:
    def test_load_into_store(self, tmp_archive):
        original = ResultStore(cycle_id="replay_test", conflict="Iran")
        original.set("sigint", {"sigint_score": 72})
        original.set("news", {"news_score": 45})
        tmp_archive.save(original)

        replay_store = tmp_archive.load_into_store("Iran", "replay_test")
        assert replay_store is not None
        assert replay_store.get("sigint")["sigint_score"] == 72
        assert replay_store.get("news")["news_score"] == 45
        assert replay_store.conflict == "Iran"
        assert replay_store.cycle_id == "replay_test"


class TestSafeDirname:
    def test_sanitizes_special_chars(self):
        assert _safe_dirname("Iran/Israel") == "Iran_Israel"
        assert _safe_dirname("Gaza Israel") == "Gaza_Israel"
        assert _safe_dirname("Taiwan-Strait") == "Taiwan-Strait"
