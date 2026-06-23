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


_META = {"view_count": 1234}
_ANALYSIS = {
    "artist": "A", "song": "S", "year": 2024, "country": "C",
    "language_ethnic_group": "L", "genre": "G", "summary": "x", "summary_short": "y",
}


@patch("ytresearch_web.download.download_video")
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail", return_value=None)
@patch("ytresearch_web.download.download_audio")
def test_archive_track_audio_only_skips_video(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    out = download.archive_track("URL", _META, _ANALYSIS, tmp_path, tmp_path, include_video=False)
    assert out["audio_path"] == str(tmp_path / "Song.mp3")
    assert out["video_path"] is None
    mock_video.assert_not_called()
    mock_tagger.write_tags.assert_called_once()


@patch("ytresearch_web.download.download_video")
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail", return_value=None)
@patch("ytresearch_web.download.download_audio")
def test_archive_track_with_video(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    mock_video.return_value = tmp_path / "Song.mp4"
    out = download.archive_track("URL", _META, _ANALYSIS, tmp_path, tmp_path, include_video=True)
    assert out["video_path"] == str(tmp_path / "Song.mp4")
    mock_video.assert_called_once()


@patch("ytresearch_web.download.download_video", side_effect=DownloadError("fail"))
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail", return_value=None)
@patch("ytresearch_web.download.download_audio")
def test_archive_track_tolerates_video_failure(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    out = download.archive_track("URL", _META, _ANALYSIS, tmp_path, tmp_path, include_video=True)
    assert out["video_path"] is None
    assert out["audio_path"] == str(tmp_path / "Song.mp3")


@patch("ytresearch_web.download.download_video")
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail")
@patch("ytresearch_web.download.download_audio")
def test_archive_track_embeds_thumbnail_and_cleans_up(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    thumb = tmp_path / "Song.jpg"
    thumb.write_text("img")
    mock_thumb.return_value = thumb
    download.archive_track("URL", _META, _ANALYSIS, tmp_path, tmp_path, include_video=False)
    mock_tagger.embed_thumbnail.assert_called_once()
    assert not thumb.exists()  # cleaned up


@patch("ytresearch_web.download.download_video")
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail")
@patch("ytresearch_web.download.download_audio")
def test_archive_track_tolerates_embed_failure_and_cleans_up(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    thumb = tmp_path / "Song.jpg"
    thumb.write_text("img")
    mock_thumb.return_value = thumb
    mock_tagger.embed_thumbnail.side_effect = Exception("embed boom")
    out = download.archive_track("URL", _META, _ANALYSIS, tmp_path, tmp_path, include_video=False)
    assert out["audio_path"] == str(tmp_path / "Song.mp3")  # did not abort
    assert not thumb.exists()  # cleaned up despite embed failure


@patch("ytresearch_web.download.download_video")
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail", return_value=None)
@patch("ytresearch_web.download.download_audio")
def test_archive_track_skips_tags_when_no_analysis(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    download.archive_track("URL", _META, None, tmp_path, tmp_path, include_video=False)
    mock_tagger.write_tags.assert_not_called()


# --- download_thumbnail: deterministic resolution (regression for data-loss bug) ---

@patch("ytresearch_web.download.subprocess.run")
def test_download_thumbnail_returns_path_matching_audio_stem(mock_run, tmp_path):
    audio = tmp_path / "Song.mp3"
    # An unrelated track's thumbnail already in the same archive dir.
    (tmp_path / "OtherTrack.jpg").write_text("not mine")
    # yt-dlp writes the thumbnail for THIS track using the same %(title)s stem.
    (tmp_path / "Song.jpg").write_text("mine")
    mock_run.return_value = _ok("")

    thumb = download.download_thumbnail("URL", audio)
    # Must pick the file matching the audio stem, never the unrelated .jpg.
    assert thumb == tmp_path / "Song.jpg"


@patch("ytresearch_web.download.subprocess.run")
def test_download_thumbnail_none_when_expected_file_absent(mock_run, tmp_path):
    audio = tmp_path / "Song.mp3"
    (tmp_path / "OtherTrack.jpg").write_text("not mine")  # present but unrelated
    mock_run.return_value = _ok("")
    # No Song.jpg was produced -> return None, do NOT return the unrelated jpg.
    assert download.download_thumbnail("URL", audio) is None


@patch("ytresearch_web.download.subprocess.run")
def test_download_thumbnail_tolerates_yt_dlp_failure(mock_run, tmp_path):
    audio = tmp_path / "Song.mp3"
    (tmp_path / "Song.jpg").write_text("mine")
    mock_run.return_value = _fail()
    assert download.download_thumbnail("URL", audio) is None


# --- timeout handling ---

@patch("ytresearch_web.download.subprocess.run")
def test_yt_dlp_timeout_raises_download_error(mock_run, tmp_path):
    import subprocess as _sp
    mock_run.side_effect = _sp.TimeoutExpired(cmd="yt-dlp", timeout=1)
    with pytest.raises(DownloadError):
        download.download_audio("URL", tmp_path)


@patch("ytresearch_web.download.subprocess.run")
def test_download_thumbnail_tolerates_timeout(mock_run, tmp_path):
    import subprocess as _sp
    audio = tmp_path / "Song.mp3"
    (tmp_path / "Song.jpg").write_text("mine")
    mock_run.side_effect = _sp.TimeoutExpired(cmd="yt-dlp", timeout=1)
    assert download.download_thumbnail("URL", audio) is None
