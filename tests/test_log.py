# -*- coding: utf-8 -*-

# Copyright (C) 2026 MURAMATSU Atsushi <amura@tomato.sakura.ne.jp>
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

"""Unit tests for eblook_mcp.log and the logging command line options."""

import logging
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from _helpers import reset_logging
from eblook_mcp import __main__ as cli
from eblook_mcp import config, log, mcp_server
from eblook_mcp.mcp_server import log_tool_errors


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    reset_logging()


class TestExpandLogfile:
    def test_all_placeholders(self) -> None:
        now = datetime(2026, 11, 25, 13, 5, 9)
        path = log.expand_logfile(
            "logs/%Y_%M_%D_%H_%m_%s.log", now)
        assert path == Path("logs/2026_11_25_13_05_09.log")

    def test_no_placeholder(self) -> None:
        assert log.expand_logfile("plain.log") == Path("plain.log")

    def test_case_sensitive(self) -> None:
        now = datetime(2026, 11, 25, 13, 5, 9)
        # %d is not one of our placeholders and stays as is.
        assert log.expand_logfile("%d.log", now) == Path("%d.log")

    def test_default_logfile(self, tmp_path: Path) -> None:
        now = datetime(2026, 11, 25)
        path = log.default_logfile(tmp_path / "config.toml", now)
        assert path == tmp_path / "2026_11_25.log"


class TestSetupLogging:
    def test_writes_to_file_and_filters_levels(self, tmp_path: Path) -> None:
        logfile = tmp_path / "sub" / "app.log"
        logger = log.setup_logging("warning", logfile)
        logger.debug("hidden")
        logger.warning("shown")
        text = logfile.read_text(encoding="utf-8")
        assert "shown" in text
        assert "hidden" not in text
        assert "WARNING" in text

    def test_repeated_setup_does_not_duplicate(self, tmp_path: Path) -> None:
        logfile = tmp_path / "app.log"
        logger = log.setup_logging("info", logfile)
        logger.info("first")
        log.setup_logging("info", logfile)
        logger.info("second")
        text = logfile.read_text(encoding="utf-8")
        assert text.count("first") == 1
        assert "second" in text

    def test_unknown_level(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="unknown log level"):
            log.setup_logging("verbose", tmp_path / "app.log")


class TestCommandLineLogging:
    def _record_setup(
            self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        recorded: dict[str, Any] = {}

        def fake_setup(level: str, path: Path) -> logging.Logger:
            recorded["level"] = level
            recorded["path"] = path
            return logging.getLogger(log.LOGGER_NAME)

        monkeypatch.setattr(log, "setup_logging", fake_setup)
        return recorded

    def test_level_without_value_disables_logging(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        recorded = self._record_setup(monkeypatch)
        monkeypatch.setattr(config, "generate_config", lambda p: "")

        assert cli.main(["--loglevel", "--gen-config", str(tmp_path)]) == 0
        assert recorded == {}

    @pytest.mark.parametrize("options", [
        ["--logfile", "app.log"],
        ["--loglevel", "--logfile", "app.log"],
    ])
    def test_logfile_requires_level(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
            capsys: pytest.CaptureFixture[str],
            options: list[str]) -> None:
        recorded = self._record_setup(monkeypatch)
        monkeypatch.setattr(config, "generate_config", lambda p: "")

        with pytest.raises(SystemExit) as excinfo:
            cli.main(options + ["--gen-config", str(tmp_path)])
        assert excinfo.value.code == 2
        assert "--logfile requires --loglevel LEVEL" in capsys.readouterr().err
        assert recorded == {}
        assert not (tmp_path / "app.log").exists()

    def test_default_path_is_next_to_config(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        recorded = self._record_setup(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setattr(config, "generate_config", lambda p: "")

        assert cli.main(["--loglevel", "debug", "--gen-config",
                         str(tmp_path)]) == 0
        path = recorded["path"]
        assert path.parent == tmp_path / "eblook_mcp"
        assert re.fullmatch(r"\d{4}_\d{2}_\d{2}\.log", path.name)

    def test_logfile_placeholders_are_expanded(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        recorded = self._record_setup(monkeypatch)
        monkeypatch.setattr(config, "generate_config", lambda p: "")

        assert cli.main([
            "--loglevel", "info",
            "--logfile", str(tmp_path / "%Y_%M_%D.log"),
            "--gen-config", str(tmp_path)]) == 0
        path = recorded["path"]
        assert path.parent == tmp_path
        assert re.fullmatch(r"\d{4}_\d{2}_\d{2}\.log", path.name)

    def test_error_is_written_with_default_path(
            self, tmp_path: Path) -> None:
        logfile = log.default_logfile(tmp_path / "config.toml")
        assert cli.main([
            "--loglevel", "error",
            "--config", str(tmp_path / "missing.toml")]) == 2
        assert "config file not found" in logfile.read_text(encoding="utf-8")

    def test_logfile_open_error(
            self, monkeypatch: pytest.MonkeyPatch,
            capsys: pytest.CaptureFixture[str]) -> None:
        def fail(level: str, path: Path) -> logging.Logger:
            raise OSError("permission denied")

        monkeypatch.setattr(log, "setup_logging", fail)
        assert cli.main(["--loglevel", "error", "--logfile", "app.log"]) == 2
        assert "cannot open log file" in capsys.readouterr().err


class TestServerErrorLogging:
    def test_unexpected_failure_is_logged(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        class FailingServer:
            def run(self, transport: str) -> None:
                raise RuntimeError("server boom")

        logfile = tmp_path / "app.log"

        def create_server(cfg: config.Config) -> FailingServer:
            return FailingServer()

        monkeypatch.setattr(mcp_server, "create_server", create_server)
        log.setup_logging("error", logfile)
        assert cli.run_server(config.Config()) == 1
        text = logfile.read_text(encoding="utf-8")
        assert "server stopped unexpectedly" in text
        assert "RuntimeError: server boom" in text


class TestToolErrorLogging:
    def test_exception_is_logged_and_reraised(self, tmp_path: Path) -> None:
        logfile = tmp_path / "app.log"

        @log_tool_errors
        def boom() -> None:
            raise ValueError("boom")

        log.setup_logging("error", logfile)
        with pytest.raises(ValueError, match="boom"):
            boom()
        text = logfile.read_text(encoding="utf-8")
        assert "boom failed" in text
        assert "ValueError: boom" in text
