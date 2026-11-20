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

"""Unit tests for eblook_mcp.common (no real dictionary required)."""

from pathlib import Path

import pytest

from eblook_mcp.common import PathEx


class TestPathEx:
    def test_unset_and_empty_setting_are_distinct(self) -> None:
        assert PathEx(None) != PathEx(Path("/tmp"))
        assert PathEx(Path("/tmp")) != PathEx(None)

    def test_same_path_is_equal(self) -> None:
        assert PathEx(Path("/tmp")) == PathEx(Path("/tmp"))

    def test_empty_values_are_equal(self) -> None:
        assert PathEx(None) == PathEx(None)
        assert hash(PathEx(None)) == hash(PathEx(None))

    def test_is_empty(self) -> None:
        assert PathEx(None).is_empty()
        assert not PathEx(Path("/tmp")).is_empty()

    def test_exists_and_is_dir(self, tmp_path: Path) -> None:
        assert PathEx(tmp_path).exists()
        assert PathEx(tmp_path).is_dir()
        assert not PathEx(tmp_path / "missing").exists()
        assert not PathEx(None).exists()

    def test_abs_str(self, tmp_path: Path) -> None:
        assert PathEx(tmp_path).abs_str() == str(tmp_path.absolute())

    def test_empty_path_raises(self) -> None:
        with pytest.raises(Exception):
            PathEx(None).get_path()
        with pytest.raises(Exception):
            PathEx(None).abs_str()
        with pytest.raises(Exception):
            PathEx(None).__fspath__()

    def test_str(self) -> None:
        assert str(PathEx(None)) == "(None)"
        assert str(PathEx(Path("/tmp"))) == "/tmp"
