"""Tests for ytresearch_web.download (no network; subprocess/tagger mocked)."""

from pathlib import Path

import pytest

from ytresearch_web import download
from ytresearch_web.download import DownloadError


def test_get_download_dirs_none_when_unset(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_AUDIO_DIR", raising=False)
    monkeypatch.delenv("DOWNLOAD_VIDEO_DIR", raising=False)
    assert download.get_download_dirs() is None


def test_get_download_dirs_returns_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("DOWNLOAD_AUDIO_DIR", str(tmp_path / "a"))
    monkeypatch.setenv("DOWNLOAD_VIDEO_DIR", str(tmp_path / "v"))
    assert download.get_download_dirs() == (tmp_path / "a", tmp_path / "v")


def test_downloads_enabled_requires_existing_dirs(monkeypatch, tmp_path):
    a, v = tmp_path / "audio", tmp_path / "video"
    monkeypatch.setenv("DOWNLOAD_AUDIO_DIR", str(a))
    monkeypatch.setenv("DOWNLOAD_VIDEO_DIR", str(v))
    assert download.downloads_enabled() is False
    a.mkdir()
    v.mkdir()
    assert download.downloads_enabled() is True


def test_validate_dir_raises_and_does_not_create(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(DownloadError):
        download._validate_dir(missing)
    assert not missing.exists()


def test_validate_dir_returns_existing(tmp_path):
    assert download._validate_dir(tmp_path) == tmp_path
