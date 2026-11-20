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

"""Utilities shared by the eblook_mcp modules."""

import os
from pathlib import Path

DEFAULT_EBLOOK = 'eblook'
DEFAULT_ESTCMD = 'estcmd'
DEFAULT_MAX_HITS = 25

class PathEx(os.PathLike[str]):
    """A path that also represents an unset/empty setting.

    ``PathEx(None)`` means "not configured" (unset or explicitly disabled),
    while ``PathEx(Path(...))`` holds a real path. Both states are hashable
    and comparable so that config values can be distinguished.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path: Path | None = Path(path) if isinstance(path, str) else path

    def __hash__(self) -> int:
        if self._path is None:
            return hash(None)
        return hash(self._path)

    def __eq__(self, rhs: object) -> bool:
        if not isinstance(rhs, PathEx):
            return NotImplemented
        return self._path == rhs._path

    def exists(self) -> bool:
        if self._path is None:
            return False
        return self._path.exists()

    def is_dir(self) -> bool:
        if self._path is None:
            return False
        return self._path.is_dir()

    def is_empty(self) -> bool:
        return self._path is None

    def get_path(self) -> Path:
        if self._path is None:
            raise Exception("PathEx is empty")
        return self._path

    def abs_str(self) -> str:
        if self._path is None:
            raise Exception("PathEx is empty")
        return str(self._path.absolute())

    def __str__(self) -> str:
        if self._path is None:
            return "(None)"
        return str(self._path)

    def __fspath__(self) -> str:
        if self._path is None:
            raise Exception("PathEx is empty")
        return self._path.__fspath__()
