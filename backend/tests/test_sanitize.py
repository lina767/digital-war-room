"""Tests for utils.sanitize."""

import pytest

from utils.sanitize import CONFLICT_MAX_LEN, sanitize_conflict


def test_sanitize_conflict_ok():
    assert sanitize_conflict("Iran") == "Iran"
    assert sanitize_conflict("Gaza/Israel") == "Gaza/Israel"
    assert sanitize_conflict("  Ukraine  ") == "Ukraine"
    assert sanitize_conflict("A-B") == "A-B"
    assert sanitize_conflict("A, B") == "A, B"


def test_sanitize_conflict_none():
    with pytest.raises(ValueError, match="conflict is required"):
        sanitize_conflict(None)


def test_sanitize_conflict_empty():
    with pytest.raises(ValueError, match="cannot be empty"):
        sanitize_conflict("")
    with pytest.raises(ValueError, match="cannot be empty"):
        sanitize_conflict("   ")


def test_sanitize_conflict_too_long():
    with pytest.raises(ValueError, match=f"longer than {CONFLICT_MAX_LEN}"):
        sanitize_conflict("x" * (CONFLICT_MAX_LEN + 1))


def test_sanitize_conflict_invalid_chars():
    with pytest.raises(ValueError, match="invalid characters"):
        sanitize_conflict("Iran<script>")
    with pytest.raises(ValueError, match="invalid characters"):
        sanitize_conflict("Iran\x00")
    with pytest.raises(ValueError, match="allows only"):
        sanitize_conflict("Iran!")
