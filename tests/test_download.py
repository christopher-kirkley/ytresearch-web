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


def test_validate_dir_rejects_file(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(DownloadError):
        download._validate_dir(f)


def test_get_download_dirs_none_when_empty_string(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_AUDIO_DIR", "")
    monkeypatch.setenv("DOWNLOAD_VIDEO_DIR", "")
    assert download.get_download_dirs() is None


from unittest.mock import MagicMock, patch


def _ok(stdout):
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ""
    return m


def _fail(stderr="boom"):
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = stderr
    return m


@patch("ytresearch_web.download.subprocess.run")
def test_download_audio_uses_no_overwrites_and_returns_path(mock_run, tmp_path):
    mock_run.return_value = _ok(str(tmp_path / "Song.mp3"))
    path = download.download_audio("URL", tmp_path)
    assert path == Path(tmp_path / "Song.mp3")
    argv = mock_run.call_args[0][0]
    assert argv[0] == "yt-dlp"
    assert "--no-overwrites" in argv


@patch("ytresearch_web.download.subprocess.run")
def test_download_audio_raises_on_failure(mock_run, tmp_path):
    mock_run.return_value = _fail("nope")
    with pytest.raises(DownloadError):
        download.download_audio("URL", tmp_path)


@patch("ytresearch_web.download.subprocess.run")
def test_download_audio_validates_dir_before_running(mock_run, tmp_path):
    with pytest.raises(DownloadError):
        download.download_audio("URL", tmp_path / "missing")
    mock_run.assert_not_called()


@patch("ytresearch_web.download.subprocess.run")
def test_download_video_uses_no_overwrites_and_returns_path(mock_run, tmp_path):
    mock_run.return_value = _ok(str(tmp_path / "Song.mp4"))
    path = download.download_video("URL", tmp_path)
    assert path == Path(tmp_path / "Song.mp4")
    assert "--no-overwrites" in mock_run.call_args[0][0]


@patch("ytresearch_web.download.subprocess.run")
def test_download_functions_use_double_dash_before_url(mock_run, tmp_path):
    mock_run.return_value = _ok(str(tmp_path / "Song.mp3"))
    for fn in (download.download_audio, download.download_video):
        mock_run.reset_mock()
        mock_run.return_value = _ok(str(tmp_path / "Song.x"))
        fn("https://example.com/watch?v=x", tmp_path)
        argv = mock_run.call_args[0][0]
        assert "--" in argv, f"{fn.__name__} argv missing -- separator"
        assert argv.index("--") == len(argv) - 2, f"{fn.__name__}: -- must be immediately before the url"
        assert argv[-1] == "https://example.com/watch?v=x"


@patch("ytresearch_web.download.subprocess.run")
def test_download_audio_raises_when_no_output_path(mock_run, tmp_path):
    mock_run.return_value = _ok("")
    with pytest.raises(DownloadError):
        download.download_audio("https://example.com/v", tmp_path)


@patch("ytresearch_web.download.subprocess.run")
def test_download_video_raises_when_no_output_path(mock_run, tmp_path):
    mock_run.return_value = _ok("")
    with pytest.raises(DownloadError):
        download.download_video("https://example.com/v", tmp_path)
