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

"""Logging setup shared by the command line and the MCP server.

Log records are written to a file, never to stdout, because stdout carries
the MCP protocol when the server runs over stdio.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

LOGGER_NAME = "eblook_mcp"

LOG_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# The placeholder letters intentionally differ from strftime: %M is the
# month, %D the day, %m the minute and %s the second.
_TIME_TOKEN = re.compile(r"%[YMDHms]")
_TIME_REPLACEMENTS = {
    "%Y": "%Y",  # year
    "%M": "%m",  # month
    "%D": "%d",  # day
    "%H": "%H",  # hour
    "%m": "%M",  # minute
    "%s": "%S",  # second
}


def expand_logfile(template: str, now: "datetime | None" = None) -> Path:
    """Expand the time placeholders in *template* and return the path."""
    moment = now if now is not None else datetime.now()

    def replace(match: "re.Match[str]") -> str:
        return moment.strftime(_TIME_REPLACEMENTS[match.group(0)])

    return Path(_TIME_TOKEN.sub(replace, template))


def default_logfile(
        config_path: Path, now: "datetime | None" = None) -> Path:
    """Return the default log file: next to config.toml, named by date."""
    return expand_logfile(str(config_path.parent / "%Y_%M_%D.log"), now)


def setup_logging(level: str, logfile: Path) -> logging.Logger:
    """Send the package logs to *logfile* at *level*.

    Any handler installed by a previous call is removed, so setting up
    twice does not duplicate log lines.
    """
    try:
        numeric = LOG_LEVELS[level.lower()]
    except KeyError:
        raise ValueError(f"unknown log level: {level}") from None
    logfile.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(logfile, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(numeric)
    logger.propagate = False
    for old in list(logger.handlers):
        logger.removeHandler(old)
        old.close()
    logger.addHandler(handler)
    return logger
