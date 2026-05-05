"""Tests for pytest plugin fixtures."""

from pathlib import Path


def test_assert_mcp_quality_passes(assert_mcp_quality):
    report = assert_mcp_quality("examples/good_server.json", min_score=80)
    assert report.score >= 80


def test_assert_mcp_quality_fails_on_bad(assert_mcp_quality):
    import pytest
    with pytest.raises(pytest.fail.Exception, match="errors"):
        assert_mcp_quality("examples/bad_server.json", min_score=80)
