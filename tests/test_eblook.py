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

"""Unit tests for eblook_mcp.eblook (no real dictionary required)."""

import base64
import logging
import re
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image

from eblook_mcp import eblook
from eblook_mcp.eblook import EBhtml, EBlook


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class FakeEBlook:
    """Minimal stand-in for EBlook used by EBhtml._eb2html."""

    def __init__(self, font: Image.Image | None = None) -> None:
        self.font = font
        self.images: list[tuple[str, int, int]] = []

    def get_image(self, ref: str,
                  format: str = "jpeg") -> bytes | Image.Image:
        if format == "jpeg":
            return b"\xff\xd8\xff\xd9"
        return Image.new("RGB", (2, 2), "red")

    def get_mono_image(self, ref: str, width: int,
                       height: int) -> Image.Image:
        self.images.append((ref, width, height))
        return Image.new("1", (width, height), 1)

    def get_font(self, code: str) -> Image.Image:
        if self.font is None:
            raise Exception(f"no font: {code}")
        return self.font


def make_html(fake: FakeEBlook | None = None,
              gaiji_map: dict[str, str] | None = None) -> EBhtml:
    """Build an EBhtml without spawning an eblook process."""
    html = EBhtml.__new__(EBhtml)
    html.eb = cast(Any, fake if fake is not None else FakeEBlook())
    html.gaiji_map = dict(gaiji_map or {})
    html.gaiji_cache = {}
    return html


def decode_data_uri(html: str) -> Image.Image:
    m = re.search(r'data:image/\w+;base64,([^"]+)', html)
    assert m is not None, html
    return Image.open(BytesIO(base64.b64decode(m.group(1))))


# ---------------------------------------------------------------------------
# mapfile / alternate.ini
# ---------------------------------------------------------------------------

class TestReadFiles:
    def test_read_mapfile(self, tmp_path: Path) -> None:
        path = tmp_path / "test.map"
        path.write_bytes(
            b"# comment\n"
            b"\n"
            b"hA121\tu00E1\ta\t#\ta\n"
            b"hA122\tu00E0\n"
            b"za233\t-\n"
            b"lonely\n")
        result = eblook.read_mapfile(path)
        assert result["ha121"] == "\u00e1"
        assert result["ha122"] == "\u00e0"
        assert result["za233"] == ""
        assert "lonely" not in result

    def test_read_alternate_ini(self, tmp_path: Path) -> None:
        path = tmp_path / "alternate.ini"
        path.write_bytes(
            b"# comment\n"
            b"u00e5\tA\n"
            b"u00e4\tB\n"
            b"broken\n")
        result = eblook.read_alternate_ini(path)
        assert result[chr(0xe5)] == "A"
        assert result[chr(0xe4)] == "B"
        assert len(result) == 2

    def test_search_mapfile_exact(self, tmp_path: Path) -> None:
        (tmp_path / "genius.map").write_bytes(b"")
        assert eblook.search_mapfile(tmp_path, "genius").get_path() == (
            tmp_path / "genius.map")

    def test_search_mapfile_case_insensitive(self, tmp_path: Path) -> None:
        # macOS filesystems are usually case-insensitive, so the exact
        # lookup may already succeed; either way the correct file is found.
        (tmp_path / "GENIUS.map").write_bytes(b"")
        found = eblook.search_mapfile(tmp_path, "genius")
        assert not found.is_empty()
        assert found.get_path().samefile(tmp_path / "GENIUS.map")

    def test_search_mapfile_missing(self, tmp_path: Path) -> None:
        assert eblook.search_mapfile(tmp_path, "nope").is_empty()

    def test_search_appendix_and_alternate(self, tmp_path: Path) -> None:
        assert eblook.search_appendix(tmp_path).is_empty()
        assert eblook.search_alternate_ini(tmp_path).is_empty()
        (tmp_path / "_appendix").mkdir()
        (tmp_path / "alternate.ini").write_bytes(b"")
        assert eblook.search_appendix(tmp_path).get_path().name == "_appendix"
        assert eblook.search_alternate_ini(tmp_path).get_path().name == (
            "alternate.ini")


# ---------------------------------------------------------------------------
# command helpers
# ---------------------------------------------------------------------------

class TestCommandHelpers:
    def setup_method(self) -> None:
        self.eb = EBlook.__new__(EBlook)

    def test_quote(self) -> None:
        assert self.eb._quote("abc") == '"abc"'
        assert self.eb._quote('a"b') == '"a\\"b"'
        assert self.eb._quote("a\\b") == '"a\\\\b"'

    def test_parse_menu(self) -> None:
        menu = self.eb._parse_menu(
            "  1. kojien 広辞苑第六版\n"
            "  2. furoku 付属資料\n"
            "noise line\n")
        assert menu == [
            (1, "kojien", "広辞苑第六版"),
            (2, "furoku", "付属資料"),
        ]


# ---------------------------------------------------------------------------
# select_book / _fulltext_search
# ---------------------------------------------------------------------------

SUBINFO = " search methods: word endword wild menu\n"


class FakeConversation(EBlook):
    """EBlook with a scripted eblook conversation (no subprocess)."""

    def __init__(self, subinfo: str = SUBINFO, *,
                 estcmd: str | None = None,
                 fulltext_idx: Path | None = None) -> None:
        self.subinfo = subinfo
        self.subbooks = [
            (1, "kojien", "広辞苑"), (2, "furoku", "付属資料")]
        self.selected_book: tuple[int, str, str] | None = None
        self.supported_method: list[str] = []
        self.use_wild = False
        self.estcmd = estcmd
        self.fulltext_idx = fulltext_idx

    def _send(self, cmd: str, error_check: bool = False) -> None:
        pass

    def _query(self, query: str) -> str:
        return self.subinfo


def make_eb(subinfo: str = SUBINFO, *, estcmd: str | None = None,
            fulltext_idx: Path | None = None) -> FakeConversation:
    """Build an EBlook with a fake eblook conversation."""
    return FakeConversation(subinfo, estcmd=estcmd, fulltext_idx=fulltext_idx)


class TestSelectBook:
    def test_select_by_tag_is_case_insensitive(self) -> None:
        eb = make_eb()
        methods = eb.select_book("KOJIEN")
        assert eb.selected_book == (1, "kojien", "広辞苑")
        assert methods == ["glob"]
        assert eb.use_wild is False

    def test_select_by_number(self) -> None:
        eb = make_eb()
        eb.select_book(2)
        assert eb.selected_book == (2, "furoku", "付属資料")

    def test_unknown_subbook_raises(self) -> None:
        with pytest.raises(Exception, match="subbook not found"):
            make_eb().select_book("nope")

    def test_wild_support_sets_use_wild(self) -> None:
        eb = make_eb(" search methods: wild menu\n")
        assert eb.select_book(1) == ["glob"]
        assert eb.use_wild is True

    def test_fulltext_is_added_when_index_exists(self) -> None:
        eb = make_eb(estcmd="/bin/estcmd", fulltext_idx=Path("/d/_ebest"))
        assert eb.select_book(1) == ["glob", "fulltext"]

    def test_book_must_be_opened_first(self) -> None:
        eb = make_eb()
        eb.subbooks = None
        with pytest.raises(Exception, match="not opended"):
            eb.select_book(1)


FULLTEXT_XML = """\
<searchresult xmlns="http://fallabs.com/hyperestraier/xmlns/search">
  <document uri="eb:kojien/1:2"><snippet>first</snippet></document>
  <document uri="eb:furoku/3:4"><snippet>other</snippet></document>
  <document uri="eb:kojien/5:6"></document>
</searchresult>
"""


class TestFulltextSearch:
    def make(self, monkeypatch: pytest.MonkeyPatch,
             xml: str = FULLTEXT_XML) -> FakeConversation:
        eb = FakeConversation(estcmd="/bin/estcmd",
                              fulltext_idx=Path("/dict/_ebest"))
        eb.selected_book = (1, "kojien", "広辞苑")
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: xml)
        return eb

    def test_only_selected_subbook_is_used(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self.make(monkeypatch)._fulltext_search("word") == [
            (1, "1:2", "first"),
            (2, "5:6", ""),
        ]

    def test_unavailable_without_index(self) -> None:
        eb = FakeConversation()
        with pytest.raises(Exception, match="not available"):
            eb._fulltext_search("word")


# ---------------------------------------------------------------------------
# _eb2html
# ---------------------------------------------------------------------------

class TestEb2Html:
    def test_indent(self) -> None:
        assert make_html()._eb2html("<ind=2>x") == (
            '<div class="ind2">x</div>')

    def test_font_bold_and_italic(self) -> None:
        html = make_html()
        assert html._eb2html("<font=bold>x</font>") == "<b>x</b>"
        assert html._eb2html("<font=italic>x</font>") == "<i>x</i>"

    def test_stray_font_close_is_ignored(self) -> None:
        # real EPWING data contains </font> without a matching <font=...>
        assert make_html()._eb2html("</font>x") == "x"

    def test_stray_prev_close_is_ignored(self) -> None:
        assert make_html()._eb2html("</prev>x") == "x"

    def test_no_newline(self) -> None:
        assert make_html()._eb2html("<no-newline>x</no-newline>") == (
            '<span class="nobr">x</span>')

    def test_em(self) -> None:
        assert make_html()._eb2html("<em>x</em>") == "<strong>x</strong>"

    def test_lone_less_than_does_not_loop(self) -> None:
        assert make_html()._eb2html("<") == "<"

    def test_unknown_tag_is_logged_and_skipped(
            self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="eblook_mcp"):
            assert make_html()._eb2html("<unknown>x") == "x"
        text = caplog.text
        assert "unknown tag unknown" in text
        # the current frame plus two callers, not the entire stack
        assert text.count('  File "') == 3
        assert "_eb2html" in text

    def test_gaiji_from_mapfile(self) -> None:
        html = make_html(gaiji_map={"za233": "あ"})
        assert html._eb2html("<gaiji=za233>") == "あ"

    def test_gaiji_falls_back_to_alt_text(self) -> None:
        assert make_html()._eb2html("<gaiji=zz999>") == "(外字:zz999)"

    def test_gaiji_as_image(self) -> None:
        html = make_html(fake=FakeEBlook(font=Image.new("1", (16, 16), 1)))
        out = html._eb2html("<gaiji=za233>")
        assert "data:image/png;base64," in out
        assert decode_data_uri(out).size == (16, 16)

    def test_gaiji_is_cached(self) -> None:
        fake = FakeEBlook(font=Image.new("1", (16, 16), 1))
        html = make_html(fake=fake)
        first = html._eb2html("<gaiji=za233>")
        second = html._eb2html("<gaiji=za233>")
        assert first == second
        assert list(html.gaiji_cache) == ["za233"]

    def test_jpeg_image(self) -> None:
        out = make_html()._eb2html("<img=jpeg>alt</img=1:2>")
        assert "data:image/jpeg;base64," in out
        assert 'alt="alt"' in out
        assert out.startswith("<br /><img")
        assert out.endswith("<br />")

    def test_bmp_image(self) -> None:
        out = make_html()._eb2html("<inline=bmp>x</inline=1:2>")
        assert "data:image/png;base64," in out

    def test_mono_image_size_from_tag(self) -> None:
        fake = FakeEBlook()
        html = make_html(fake=fake)
        out = html._eb2html("<inline=mono:16x8></inline=1:2>")
        assert fake.images == [("1:2", 16, 8)]
        assert decode_data_uri(out).size == (16, 8)

    def test_unknown_image_format_raises(self) -> None:
        with pytest.raises(Exception, match="unknow image format"):
            make_html()._eb2html("<img=gif>x</img=1:2>")

    def test_reference_link(self) -> None:
        html = make_html()
        assert html._eb2html(
            "<reference>x</reference=1:2>", ignore_link=False) == (
            '<a href="1:2">x</a>')
        assert html._eb2html(
            "<reference>x</reference=1:2>", ignore_link=True) == "x"

    def test_nested_indent_closes_previous_div(self) -> None:
        assert make_html()._eb2html("<ind=1>a<ind=2>b") == (
            '<div class="ind1">a</div><div class="ind2">b</div>')

    def test_indent_closed_at_newline(self) -> None:
        assert make_html()._eb2html("<ind=1>a\nb") == (
            '<div class="ind1">a</div>b')

    def test_next_marker_truncates(self) -> None:
        assert make_html()._eb2html("x<next>y</next>") == "x"

    def test_prev_marker_truncates(self) -> None:
        assert make_html()._eb2html("x<prev>y</prev>") == "x"

    def test_sub_and_sup(self) -> None:
        assert make_html()._eb2html("<sub>2</sub><sup>3</sup>") == (
            "<sub>2</sub><sup>3</sup>")

    def test_sound_and_movie_tags_are_dropped(self) -> None:
        assert make_html()._eb2html("<snd=1>x</snd><mov=2>") == "x"

    def test_image_without_end_tag_raises(self) -> None:
        with pytest.raises(Exception, match="cannot found"):
            make_html()._eb2html("<img=jpeg>alt")

    def test_image_with_wrong_end_tag_raises(self) -> None:
        with pytest.raises(Exception, match="unkonw tag"):
            make_html()._eb2html("<img=jpeg>alt</inline=1:2>")

    def test_invalid_mono_image_size_raises(self) -> None:
        with pytest.raises(Exception, match="unknow image format"):
            make_html()._eb2html("<inline=mono:ax></inline=1:2>")
