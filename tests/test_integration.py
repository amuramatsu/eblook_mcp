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

"""Integration tests using real dictionaries.

These tests are skipped unless eblook and the dictionaries are available.
Set EBLOOK_DICT_ROOT to point at another dictionary directory.
"""

from pathlib import Path

import pytest

from _helpers import DICT_ROOT, requires_dictionary, requires_eblook
from eblook_mcp import config, eblook
from eblook_mcp.common import DEFAULT_MAX_HITS

pytestmark = [requires_eblook, pytest.mark.integration]


def link_dictionary(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    link = directory / name
    link.symlink_to(DICT_ROOT / name)
    return link


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@requires_dictionary("koujien")
def test_search_and_content() -> None:
    with eblook.EBhtml() as eh:
        books = eh.set_book(DICT_ROOT / "koujien")
        assert len(books) > 0
        methods = eh.select_book(1)
        assert "glob" in methods
        html = eh.search("楽器")
    assert "<h2>" in html
    assert "楽器" in html


@requires_dictionary("GENIUS_DAIEIWA")
def test_alternate_ini_translation() -> None:
    with eblook.EBhtml() as eh:
        eh.set_book(DICT_ROOT / "GENIUS_DAIEIWA")
        eh.select_book(1)
        html = eh.search("Gödel")
    assert "Gö" in html
    assert "del" in html


@requires_dictionary("scitech_EJ-JE")
def test_fulltext_search() -> None:
    with eblook.EBhtml() as eh:
        eh.set_book(DICT_ROOT / "scitech_EJ-JE")
        methods = eh.select_book(1)
        assert "fulltext" in methods
        html = eh.search("pearl", method="fulltext")
    assert "<h2>" in html
    assert len(html) > 100


@requires_dictionary("cdw12_dan")
def test_max_hits_is_applied() -> None:
    with eblook.EBlook() as eb:
        eb.set_book(DICT_ROOT / "cdw12_dan")
        eb.select_book(1)
        hits = eb.search("*")
    assert 0 < len(hits) <= DEFAULT_MAX_HITS


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

def test_close_terminates_process() -> None:
    eb = eblook.EBlook()
    proc = eb.eblook
    assert proc is not None
    eb.close()
    assert eb.eblook is None
    # poll() is more reliable than os.kill(pid, 0), which can hit a reused pid
    assert proc.proc.poll() is not None
    eb.close()  # idempotent


def test_closed_instance_rejects_commands() -> None:
    eb = eblook.EBlook()
    eb.close()
    with pytest.raises(Exception, match="already closed"):
        eb._query("list")


def test_ebhtml_passes_max_hits() -> None:
    with eblook.EBhtml(max_hits=4) as eh:
        assert eh.eb.max_hits == 4


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@requires_dictionary("cdw12_dan")
def test_generated_config_round_trip(tmp_path: Path) -> None:
    link_dictionary(tmp_path, "cdw12_dan")
    text = config.generate_config(tmp_path)
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")

    cfg = config.load_config(path)
    assert cfg.max_hits == DEFAULT_MAX_HITS
    assert len(cfg.dictionaries) >= 1

    entry = next(iter(cfg.dictionaries.values()))
    with cfg.new_eblook() as eb:
        eb.set_book(entry.path, entry.appendix, entry.alternate_ini)
        eb.select_book(entry.subbook)
        hits = eb.search("hus*")
    assert len(hits) > 0


@requires_dictionary("cdw12_dan")
def test_relative_paths_in_config(tmp_path: Path) -> None:
    link_dictionary(tmp_path / "dicts", "cdw12_dan")
    path = tmp_path / "config.toml"
    path.write_text(
        '[[dictionaries."dan:sandic29"]]\n'
        'path = "dicts/cdw12_dan"\n'
        'subbook = "sandic29"\n'
        'alternate_ini = "dicts/cdw12_dan/alternate.ini"\n'
        'mapfile = "dicts/cdw12_dan/sandic29.map"\n',
        encoding="utf-8")

    cfg = config.load_config(path)
    entry = cfg.dictionaries["dan:sandic29"]
    assert entry.path == tmp_path / "dicts" / "cdw12_dan"
    assert entry.mapfile is not None
    assert entry.alternate_ini is not None
    assert entry.mapfile.get_path().is_file()
    assert entry.alternate_ini.get_path().is_file()

    with cfg.new_eblook() as eb:
        eb.set_book(entry.path, entry.appendix, entry.alternate_ini)
        eb.select_book(entry.subbook)
        hits = eb.search("hus*")
    assert len(hits) > 0


@requires_dictionary("GENIUS_DAIEIWA")
def test_generated_config_with_appendix(tmp_path: Path) -> None:
    link_dictionary(tmp_path, "GENIUS_DAIEIWA")
    path = tmp_path / "config.toml"
    path.write_text(config.generate_config(tmp_path), encoding="utf-8")

    cfg = config.load_config(path)
    entry = next(iter(cfg.dictionaries.values()))
    assert entry.appendix is not None
    assert not entry.appendix.is_empty()

    with cfg.new_eblook() as eb:
        eb.set_book(entry.path, entry.appendix, entry.alternate_ini)
        eb.select_book(entry.subbook)
        hits = eb.search("Gödel")
    assert len(hits) > 0
