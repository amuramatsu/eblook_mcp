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

"""Shared helpers for the test suite."""

import logging
import os
import shutil
from pathlib import Path

import pytest

from eblook_mcp.log import LOGGER_NAME

# Dictionaries are not part of the repository. Tests that need a real
# dictionary are skipped when it cannot be found.
DICT_ROOT = Path(os.environ.get("EBLOOK_DICT_ROOT", "/usr/local/share/dict"))

requires_eblook = pytest.mark.skipif(
    shutil.which("eblook") is None,
    reason="eblook command is not available")


def requires_dictionary(*names: str) -> pytest.MarkDecorator:
    missing = [name for name in names if not (DICT_ROOT / name).is_dir()]
    return pytest.mark.skipif(
        bool(missing),
        reason="dictionary not found: "
               + ", ".join(str(DICT_ROOT / name) for name in missing))


def reset_logging() -> None:
    """Undo setup_logging() so tests do not leak handlers to each other."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
