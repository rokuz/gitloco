from pathlib import Path

from gitloco.app import _display_path


def test_path_under_home_collapses_to_tilde(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _display_path(tmp_path / "Dev" / "Projects" / "foo") == "~/Dev/Projects/foo"


def test_path_equal_to_home_returns_tilde_only(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _display_path(tmp_path) == "~"


def test_path_outside_home_stays_absolute(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    outside = tmp_path / "other" / "elsewhere"
    assert _display_path(outside) == str(outside)


def test_handles_path_home_failure(monkeypatch):
    def boom():
        raise RuntimeError("no home for you")

    monkeypatch.setattr(Path, "home", staticmethod(boom))
    assert _display_path(Path("/some/abs/path")) == "/some/abs/path"
