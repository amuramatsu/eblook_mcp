# -*- coding: utf-8 -*-

# Copyright (C) MURAMATSU Atsushi <amura@tomato.sakura.ne.jp>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""Unit tests for eblook_mcp.config (no real dictionary required)."""

import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from _helpers import reset_logging
from eblook_mcp import __version__, config, eblook
from eblook_mcp.common import DEFAULT_EBLOOK, DEFAULT_ESTCMD, DEFAULT_MAX_HITS

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]

from eblook_mcp.__main__ import main


ENTRY: dict[str, Any] = {
    "title": 'A "quoted" title',
    "description": "",
    "path": "/dicts/bundle",
    "subbook": "tag",
    "appendix": "",
    "alternate_ini": "/dicts/bundle/alternate.ini",
    "mapfile": "/dicts/bundle/tag.map",
    "method": ["glob"],
}


def toml(text: str) -> dict[str, Any]:
    return tomllib.loads(text)


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    reset_logging()


# ---------------------------------------------------------------------------
# generate_config
# ---------------------------------------------------------------------------

class TestGenerateConfig:
    def test_format(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            config, "search_dictionary", lambda p: {"bundle:tag": dict(ENTRY)})
        text = config.generate_config(tmp_path)
        data = toml(text)

        assert data["eblook"] == ""
        assert data["estcmd"] == ""
        assert data["max_hits"] == DEFAULT_MAX_HITS
        assert "alternate_ini" not in data

        entry = data["dictionaries"]["bundle:tag"][0]
        assert entry["title"] == 'A "quoted" title'
        assert entry["path"] == "/dicts/bundle"
        assert entry["subbook"] == "tag"
        assert entry["appendix"] == ""
        assert entry["alternate_ini"] == "/dicts/bundle/alternate.ini"
        assert entry["mapfile"] == "/dicts/bundle/tag.map"
        # bare keys cannot contain ':', so the key must be quoted
        assert '[[dictionaries."bundle:tag"]]' in text

    def test_absolute_paths_are_emitted(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            config, "search_dictionary", lambda p: {"b:t": dict(ENTRY)})
        data = toml(config.generate_config(tmp_path))
        assert data["dictionaries"]["b:t"][0]["path"].startswith("/")

    def test_toml_string_escaping(self) -> None:
        assert config._toml_str('a"b\\c\nd\te\x01') == (
            '"a\\"b\\\\c\\nd\\te\\u0001"')

    def test_missing_directory(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not a directory"):
            config.search_dictionary(tmp_path / "missing")


# ---------------------------------------------------------------------------
# parse_config / load_config
# ---------------------------------------------------------------------------

class TestParseConfig:
    def test_minimal_entry(self, tmp_path: Path) -> None:
        cfg = config.parse_config(
            toml('[[dictionaries."b:t"]]\npath = "dicts/b"\nsubbook = "t"\n'),
            tmp_path / "config.toml")
        entry = cfg.dictionaries["b:t"]
        assert entry.path == tmp_path / "dicts/b"
        assert entry.subbook == "t"
        assert entry.title == ""
        assert entry.appendix is None
        assert entry.alternate_ini is None
        assert entry.mapfile is None
        assert cfg.max_hits == DEFAULT_MAX_HITS

    def test_single_table_form(self, tmp_path: Path) -> None:
        cfg = config.parse_config(
            toml('[dictionaries.b]\npath = "/d"\nsubbook = "t"\n'),
            tmp_path / "config.toml")
        assert cfg.dictionaries["b"].subbook == "t"

    def test_three_state_paths(self, tmp_path: Path) -> None:
        cfg = config.parse_config(toml(
            '[dictionaries.b]\npath = "/d"\nsubbook = "t"\n'
            'appendix = ""\n'
            'alternate_ini = "alt.ini"\n'), tmp_path / "config.toml")
        entry = cfg.dictionaries["b"]
        assert entry.appendix is not None and entry.appendix.is_empty()
        assert entry.alternate_ini is not None
        assert entry.alternate_ini.get_path() == tmp_path / "alt.ini"
        assert entry.mapfile is None

    def test_absolute_path_is_kept(self, tmp_path: Path) -> None:
        cfg = config.parse_config(
            toml('[dictionaries.b]\npath = "/d"\nsubbook = "t"\n'
                 'mapfile = "/m.map"\n'), tmp_path / "config.toml")
        mapfile = cfg.dictionaries["b"].mapfile
        assert mapfile is not None
        assert mapfile.get_path() == Path("/m.map")

    def test_relative_paths_are_normalised(self, tmp_path: Path) -> None:
        cfg = config.parse_config(
            toml('[dictionaries.b]\npath = "../dicts/b"\nsubbook = "t"\n'),
            tmp_path / "sub" / "config.toml")
        assert cfg.dictionaries["b"].path == tmp_path / "dicts/b"
        assert ".." not in str(cfg.dictionaries["b"].path)

    def test_relative_path_without_config_path(self) -> None:
        cfg = config.parse_config(
            toml('[dictionaries.b]\npath = "dicts/b"\nsubbook = "t"\n'))
        assert cfg.dictionaries["b"].path == Path("dicts/b")

    @pytest.mark.parametrize("value", ['"25"', "-1", "true"])
    def test_invalid_max_hits(self, value: str) -> None:
        with pytest.raises(ValueError, match="max_hits"):
            config.parse_config(toml(f"max_hits = {value}\n"))

    def test_max_hits(self) -> None:
        assert config.parse_config(toml("max_hits = 0\n")).max_hits == 0
        assert config.parse_config(toml("max_hits = 5\n")).max_hits == 5

    def test_commands(self, tmp_path: Path) -> None:
        cfg = config.parse_config(toml(""), tmp_path / "config.toml")
        assert cfg.eblook_cmd == DEFAULT_EBLOOK
        assert cfg.estcmd_cmd == DEFAULT_ESTCMD

        cfg = config.parse_config(
            toml('eblook = "bin/eblook"\nestcmd = "estcmd"\n'),
            tmp_path / "config.toml")
        assert cfg.eblook_cmd == str(tmp_path / "bin" / "eblook")
        assert cfg.estcmd_cmd == "estcmd"

    def test_global_alternate_ini_disabled(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = config.parse_config(toml('alternate_ini = ""\n'))
        assert cfg.alternate_ini is None

    def test_global_alternate_ini_relative(self, tmp_path: Path) -> None:
        (tmp_path / "alt.ini").write_bytes(b"")
        cfg = config.parse_config(
            toml('alternate_ini = "alt.ini"\n'), tmp_path / "config.toml")
        assert cfg.alternate_ini == tmp_path / "alt.ini"

    def test_global_alternate_ini_missing_warns(
            self, tmp_path: Path,
            caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="eblook_mcp"):
            cfg = config.parse_config(
                toml('alternate_ini = "missing.ini"\n'),
                tmp_path / "config.toml")
        assert cfg.alternate_ini is None
        assert "alternate.ini not found" in caplog.text

    def test_global_alternate_ini_default(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        alt = tmp_path / "eblook_mcp" / "alternate.ini"
        alt.parent.mkdir()
        alt.write_bytes(b"")
        assert config.parse_config(toml("")).alternate_ini == alt

    def test_missing_required_keys(self) -> None:
        with pytest.raises(ValueError, match="missing 'path'"):
            config.parse_config(toml("[dictionaries.b]\nsubbook = \"t\"\n"))
        with pytest.raises(ValueError, match="missing 'subbook'"):
            config.parse_config(toml("[dictionaries.b]\npath = \"/d\"\n"))

    def test_duplicate_entries(self) -> None:
        with pytest.raises(ValueError, match="expected one table"):
            config.parse_config(toml(
                '[[dictionaries.b]]\npath = "/a"\nsubbook = "t"\n'
                '[[dictionaries.b]]\npath = "/b"\nsubbook = "t"\n'))

    def test_non_string_path(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            config.parse_config(
                toml('[dictionaries.b]\npath = "/d"\nsubbook = "t"\n'
                     "appendix = 1\n"))


class TestLoadConfig:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            config.load_config(tmp_path / "config.toml")

    def test_invalid_toml(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text("dictionaries = [\n", encoding="utf-8")
        with pytest.raises(ValueError):
            config.load_config(path)

    def test_relative_paths_from_file(self, tmp_path: Path) -> None:
        (tmp_path / "dicts").mkdir()
        path = tmp_path / "config.toml"
        path.write_text(
            '[dictionaries.b]\npath = "dicts/b"\nsubbook = "t"\n',
            encoding="utf-8")
        cfg = config.load_config(path)
        assert cfg.path == path
        assert cfg.dictionaries["b"].path == tmp_path / "dicts" / "b"

    def test_default_path_uses_xdg(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        expected = tmp_path / "eblook_mcp" / "config.toml"
        assert config.default_config_path() == expected
        expected.parent.mkdir()
        expected.write_text("max_hits = 7\n", encoding="utf-8")
        assert config.load_config().max_hits == 7


class TestNewEBlook:
    def test_arguments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded: dict[str, tuple[Any, ...]] = {}

        class Fake:
            def __init__(self, *args: object) -> None:
                recorded["args"] = args

        monkeypatch.setattr(eblook, "EBlook", Fake)
        cfg = config.Config(
            eblook_cmd="/bin/eblook",
            estcmd_cmd="/bin/estcmd",
            alternate_ini=Path("/alt.ini"),
            max_hits=3)
        cfg.new_eblook()
        assert recorded["args"] == (
            "/bin/eblook", "/bin/estcmd", Path("/alt.ini"), 3)


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------

class TestCommandLine:
    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0
        assert __version__ in capsys.readouterr().out

    def test_gen_config(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
            capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(
            config, "generate_config", lambda p: "max_hits = 25\n")
        assert main(["--gen-config", str(tmp_path)]) == 0
        # only the trailing newline added by print is significant
        assert capsys.readouterr().out.rstrip("\n") == "max_hits = 25"

    def test_gen_config_error(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        def fail(path: Path) -> None:
            raise ValueError("not a directory")

        monkeypatch.setattr(config, "generate_config", fail)
        logfile = tmp_path / "error.log"
        assert main([
            "--loglevel", "error", "--logfile", str(logfile),
            "--gen-config", str(tmp_path)]) == 2
        assert "not a directory" in logfile.read_text(encoding="utf-8")

    def test_config_load_error(self, tmp_path: Path) -> None:
        logfile = tmp_path / "error.log"
        assert main([
            "--loglevel", "error", "--logfile", str(logfile),
            "--config", str(tmp_path / "missing.toml")]) == 2
        assert "config file not found" in logfile.read_text(encoding="utf-8")

    def test_invalid_loglevel(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--loglevel", "verbose"])
        assert excinfo.value.code == 2

    def test_server_is_started(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from eblook_mcp import __main__ as cli

        started: list[config.Config] = []

        def run_server(cfg: config.Config) -> int:
            started.append(cfg)
            return 0

        monkeypatch.setattr(
            config, "load_config", lambda path=None: config.Config())
        monkeypatch.setattr(cli, "run_server", run_server)

        assert main([]) == 0
        assert len(started) == 1

    def test_mutually_exclusive(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--config", "a.toml", "--gen-config", "dir"])
        assert excinfo.value.code == 2
