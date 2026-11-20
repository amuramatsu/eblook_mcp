#! /usr/bin/env python3
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

import os
import re
import signal
import base64
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from io import BytesIO
from tempfile import NamedTemporaryFile
from typing import TypeAlias

from PIL import Image
from pexpect import EOF
from pexpect.popen_spawn import PopenSpawn

from .common import PathEx, DEFAULT_EBLOOK, DEFAULT_ESTCMD, DEFAULT_MAX_HITS

EBLOOK_MENU = list[tuple[int, str, str]]

GLOBAL_ALTERNATE_INI = None

CSS_TEXT = """
.ind0{text-indent: 0em;}
.ind1{text-indent: 1em;}
.ind2{text-indent: 2em;}
.ind3{text-indent: 3em;}
.ind4{text-indent: 4em;}
.ind5{text-indent: 5em;}
.ind6{text-indent: 6em;}
.ind7{text-indent: 7em;}
.ind8{text-indent: 8em;}
.ind9{text-indent: 9em;}
.nobr{white-space: nowrap;}
"""

DEFAULT_SEARCH_TRANSLATE = {
    "\u00a1": "!",
    "\u00a2": "\uffe0", # ￠
    "\u00a3": "\uffe1", # ￡
    "\u00a5": "\\",
    "\u00a6": "|",
    "\u00a9": "c",
    "\u00aa": "a",
    "\u00ab": "\u226a", # ≪
    "\u00ac": "\uffe2", # ￢
    "\u00ad": "-",
    "\u00ae": "R",
    "\u00af": "\uffe3", # ￣

    "\u00b2": "2",
    "\u00b3": "3",
    "\u00b5": "\u03bc", # μ
    "\u00b7": "\u30fb", # ・
    "\u00b8": "\uff0c", # 、
    "\u00b9": "1",
    "\u00ba": "o",
    "\u00bb": "\u226b", # ≫

    "\u00c0": "A",
    "\u00c1": "A",
    "\u00c2": "A",
    "\u00c3": "A",
    "\u00c4": "A",
    "\u00c5": "A",
    "\u00c6": "A",
    "\u00c7": "C",
    "\u00c8": "E",
    "\u00c9": "E",
    "\u00ca": "E",
    "\u00cb": "E",
    "\u00cc": "I",
    "\u00cd": "I",
    "\u00ce": "I",
    "\u00cf": "I",

    "\u00d0": "D",
    "\u00d1": "N",
    "\u00d2": "O",
    "\u00d3": "O",
    "\u00d4": "O",
    "\u00d5": "O",
    "\u00d6": "O",
    "\u00d8": "O",
    "\u00d9": "U",
    "\u00da": "U",
    "\u00db": "U",
    "\u00dc": "U",
    "\u00dd": "Y",
    "\u00de": "T",
    "\u00df": "s",

    "\u00e0": "a",
    "\u00e1": "a",
    "\u00e2": "a",
    "\u00e3": "a",
    "\u00e4": "a",
    "\u00e5": "a",
    "\u00e6": "a",
    "\u00e7": "c",
    "\u00e8": "e",
    "\u00e9": "e",
    "\u00ea": "e",
    "\u00eb": "e",
    "\u00ec": "i",
    "\u00ed": "i",
    "\u00ee": "i",
    "\u00ef": "i",

    "\u00f0": "d",
    "\u00f1": "n",
    "\u00f2": "o",
    "\u00f3": "o",
    "\u00f4": "o",
    "\u00f5": "o",
    "\u00f6": "o",
    "\u00f8": "o",
    "\u00f9": "u",
    "\u00fa": "u",
    "\u00fb": "u",
    "\u00fc": "u",
    "\u00fd": "y",
    "\u00fe": "t",
    "\u00ff": "y",
    "\u3094": "ヴ",
}    

def search_appendix(path: Path) -> PathEx:
    p = path / "_appendix"
    if p.exists() and p.is_dir():
        return PathEx(p)
    return PathEx(None)

def search_alternate_ini(path: Path) -> PathEx:
    p = path / "alternate.ini"
    if p.exists() and p.is_file():
        return PathEx(p)
    return PathEx(None)

def search_mapfile(path: Path, tag: str) -> PathEx:
    p = path / (tag + ".map")
    if p.exists() and p.is_file():
        return PathEx(p)
    tag = tag.lower()
    for n in path.glob("*.map"):
        if n.stem.lower() == tag:
            return PathEx(n)
    return PathEx(None)

def read_mapfile(path: Path) -> dict[str, str]:
    mapfile = {}
    with open(path, encoding='latin-1') as f:
        for line in f:
            line = line.rstrip(' \r\n')
            if line == "" or line[0] == "#":
                continue
            data = line.split()
            if len(data) < 2:
                continue
            key = data[0].lower()
            value = ""
            if data[1] != "-":
                for v in data[1].split(','):
                    v = v.lower().lstrip('u')
                    value += chr(int(v, 16))
            mapfile[key] = value
    return mapfile

def read_alternate_ini(path: Path) -> dict[str, str]:
    inifile = {}
    with open(path, encoding='cp932') as f:
        for line in f:
            line = line.rstrip(' \t\r\n')
            if line == "" or line[0] == "#":
                continue
            data = line.split("\t")
            if len(data) < 2:
                continue
            key_s, value = data[:2]
            key_s = key_s.lower().lstrip('u')
            inifile[chr(int(key_s, 16))] = value
    return inifile

class EBlook:
    def __init__(self,
                 eblook: str=DEFAULT_EBLOOK,
                 estcmd: str=DEFAULT_ESTCMD,
                 global_alternate_ini: Path|None=GLOBAL_ALTERNATE_INI,
                 max_hits: int=DEFAULT_MAX_HITS):
        if max_hits < 0:
            raise ValueError(f"max_hits must be >= 0: {max_hits}")
        self.estcmd = shutil.which(estcmd)
        eblook_path = shutil.which(eblook)
        if eblook_path is None:
            raise FileNotFoundError(f"eblook command not found: {eblook}")
        self.eblook_bin = eblook_path
        proc = PopenSpawn(
            [ eblook_path, "-e", "euc-jp", "-i", "-q" ],
            encoding="euc-jp", codec_errors="ignore")
        self.eblook: PopenSpawn[str] | None = proc
        self.subbooks: EBLOOK_MENU | None = None
        self.selected_book: tuple[int, str, str] | None = None
        self.supported_method: list[str] = []
        self.search_translate: dict[int, str] | None = None
        self.use_wild = False
        self.fulltext_idx: Path | None = None
        self.global_alternate_ini = global_alternate_ini
        self.max_hits = max_hits

        proc.expect("eblook> ")
        self._send(f"set max-hits {max_hits}")
        self._send("set max-text 0")
        self._send("set escape-text true")
        self._send("set decorate-mode on")
        self._send("set search-method glob")

    def close(self) -> None:
        eb = self.eblook
        if eb is None:
            return
        self.eblook = None
        try:
            eb.sendline("quit")
            eb.expect(EOF, timeout=3)
        except Exception:
            pass
        finally:
            try:
                if eb.proc.poll() is None:
                    eb.kill(signal.SIGKILL)
            except Exception:
                pass
            try:
                eb.wait()  # type: ignore[no-untyped-call]
            except Exception:
                pass

    def __enter__(self) -> "EBlook":
        return self

    def __exit__(self, exc_type: object, exc_value: object,
                 traceback: object) -> None:
        self.close()

    def _update_search_translate(self, local_alternate: PathEx) -> None:
        d = dict(DEFAULT_SEARCH_TRANSLATE)
        if self.global_alternate_ini:
            d.update(read_alternate_ini(self.global_alternate_ini))
        if local_alternate.exists():
            d.update(read_alternate_ini(local_alternate.get_path()))
        self.search_translate = str.maketrans(d)

    def _send(self, cmd: str, error_check: bool=False) -> None:
        if self.eblook is None:
            raise Exception("eblook is already closed")
        self.eblook.sendline(cmd)
        self.eblook.expect("eblook> ")
        if error_check and self.eblook.before != "":
            raise Exception(self.eblook.before)

    def _query(self, query: str) -> str:
        if self.eblook is None:
            raise Exception("eblook is already closed")
        self.eblook.sendline(query)
        self.eblook.expect("eblook> ")
        before = self.eblook.before
        return "" if before is None else str(before)

    def _quote(self, s: str) -> str:
        s = s.replace("\\", "\\\\")
        s = s.replace('"', '\\"')
        return f'"{s}"'

    MENU_RE = re.compile(r'^\s*(\d+).\s*([^\s]+)\s+(.*)$')
    def _parse_menu(self, s: str) -> EBLOOK_MENU:
        result = []
        for line in s.split("\n"):
            m = self.MENU_RE.match(line)
            if m:
                result.append((int(m.group(1)), m.group(2), m.group(3)))
        return result

    def set_book(
            self, path: Path,
            appendix: PathEx|None=None,
            alternate_ini: PathEx|None=None,
    ) -> EBLOOK_MENU:
        if appendix is None:
            appendix = search_appendix(path)
        if alternate_ini is None:
            alternate_ini = search_alternate_ini(path)

        s = '{}'.format(self._quote(str(path.absolute())))
        if appendix.exists():
            s += ' {}'.format(self._quote(appendix.abs_str()))
        self._send("book " + s, error_check=True)
        books: EBLOOK_MENU = []
        self.subbooks = books
        self.selected_book = None
        self.supported_method = []
        self.use_wild = False
        idx = path / "_ebest"
        self.fulltext_idx = idx if idx.exists() else None
        self._update_search_translate(alternate_ini)
             
        for num, tag, title in self._parse_menu(self._query("list")):
            title = title.replace('\u3000', ' ')
            books.append((num, tag, title))
        return books

    def select_book(self, num_or_tag: int|str) -> list[str]:
        self.selected_book = None
        self.supported_method = []
        self.use_wild = False
        if self.subbooks is None:
            raise Exception("Book is not opended yet")
        self._send("select {}".format(num_or_tag), error_check=True)
        if isinstance(num_or_tag, int):
            for num, tag, title in self.subbooks:
                if num == num_or_tag:
                    self.selected_book = (num, tag.lower(), title)
        else:
            assert isinstance(num_or_tag, str)
            for num, tag, title in self.subbooks:
                if tag.lower() == num_or_tag.lower():
                    self.selected_book = (num, tag.lower(), title)
        if self.selected_book is None:
            raise Exception(f"subbook not found: {num_or_tag}")
        q = self._query("subinfo")
        result = []
        for line in q.splitlines():
            line = line.rstrip("\r\n")
            if line.startswith(" search methods:"):
                result = line.split()[2:]
                break
        if "endword" not in result and "wild" in result:
            self.use_wild = True
        for v in ('word', 'endword', 'wild',
                  'copyriht', 'menu', 'color_chart'):
            if v in result:
                result.remove(v)
        self.supported_method = [ "glob" ] + result
        if self.estcmd is not None and self.fulltext_idx is not None:
            self.supported_method += [ "fulltext" ]
        return self.supported_method

    def _fulltext_search(self, word: str) -> EBLOOK_MENU:
        result: EBLOOK_MENU = []
        if self.estcmd is None or self.fulltext_idx is None:
            raise Exception("fulltext search is not available")
        s = subprocess.check_output([
            self.estcmd, "search", "-sf", "-vx",
            str(self.fulltext_idx.absolute()),
            word
        ], encoding='utf-8')
        NS = "{http://fallabs.com/hyperestraier/xmlns/search}"

        root = ET.fromstring(s)
        num = 1
        for el in root.findall(f'{NS}document'):
            uri = el.get("uri")
            if uri is None or self.selected_book is None:
                continue
            if uri.startswith(f'eb:{self.selected_book[1]}/'):
                ref = uri.split('/', 2)[1]
                title = el.findtext(f'{NS}snippet') or ""
                result.append((num, ref, title))
                num += 1
        return result
    
    def search(self, word: str, method: str="glob") -> EBLOOK_MENU:
        if self.selected_book is None:
            raise Exception("Book is not selected yet")
        if word == "":
            raise ValueError("search word is empty")
        if method not in self.supported_method:
            method = "glob"

        if method == "fulltext":
            return self._fulltext_search(word)
        if method == "glob" and self.use_wild and word[0] == "*":
            method = "wild"

        # eblook の glob にある問題を回避するため、できるだけ別methodにする
        if method == "glob":
            if word[0] == '*':
                method = "endword"
                word = word[1:]
            elif word[-1] == '*':
                method = "word"
                word = word[:-1]
            elif "exactword" in self.supported_method:
                method = "exact"
        if method == "exactword":
            method = "exact"
        if word == "":
            raise ValueError("search word is empty after removing '*'")
        
        self._send(f'set search-method {method}')
        if self.search_translate is None:
            raise Exception("search translate is not initialized")
        word = word.translate(self.search_translate)
        s = self._query('search {}'.format(self._quote(word)))
        if s in ("You should specify a book directory first",
                 "You should select a subbook first"):
            raise Exception(s)
        return self._parse_menu(s)

    def search_keyword(self, words: list[str]) -> EBLOOK_MENU:
        if "keyword" not in self.supported_method:
            raise Exception("keyword search is not supported")
        return self.search("=" + "=".join(words), method="keyword")

    def search_multi(self, words: list[str]) -> EBLOOK_MENU:
        if "multi" not in self.supported_method:
            raise Exception("multi search is not supported")
        return self.search(":" + ":".join(words), method="multi")
        
    def search_cross(self, words: list[str]) -> EBLOOK_MENU:
        if "cross" not in self.supported_method:
            raise Exception("cross search is not supported")
        return self.search("&" + "&".join(words), method="cross")
        
    def get_content(self, entry: str) -> str:
        s = self._query(f'content -{entry}')
        if (s.startswith("No search has been executed yet.") or
            s.startswith("Invalid entry number:")):
            raise Exception(s)
        return s

    def get_image(self, entry: str, format: str='jpeg') -> bytes | Image.Image:
        tmp = None
        try:
            if format == "jpeg":
                tmp = NamedTemporaryFile(suffix='.jpg', delete=False)
                tmp.close()
                self._send('jpg {} {}'.format(entry, self._quote(tmp.name)))
                with open(tmp.name, 'rb') as f:
                    return f.read()
            elif format == 'bmp':
                tmp = NamedTemporaryFile(suffix='.bmp', delete=False)
                tmp.close()
                self._send('bmp {} {}'.format(entry, self._quote(tmp.name)))
                img = Image.open(tmp.name)
                img.load()
                return img
            else:
                raise Exception(f"unknown format {format}")
        finally:
            if tmp is not None:
                os.unlink(tmp.name)

    def get_mono_image(self, entry: str, width: int, height: int) -> Image.Image:
        s = self._query(f'pbm {entry} {width} {height}')
        f = BytesIO(s.encode('ascii'))
        return Image.open(f, formats=['PPM'])

    def get_sound(self, entry_start: str, entry_end: str) -> bytes:
        tmp = NamedTemporaryFile(suffix='.wav', delete=False)
        try:
            tmp.close()
            self._send('wav {} {} {}'.format(
                entry_start, entry_end, self._quote(tmp.name)))
            with open(tmp.name, 'rb') as f:
                return f.read()
        finally:
            os.unlink(tmp.name)

    def get_mpeg_path(self, id0: str, id1: str, id2: str, id3: str) -> Path:
        s = self._query(f'mpeg_path {id0} {id1} {id2} {id3}')
        if s == "":
            raise Exception(f"Cannot found movie({id0} {id1} {id2} {id3})")
        return Path(s)
    
    def get_font(self, fontid: str) -> Image.Image:
        s = self._query(f'font {fontid}')
        if s.startswith("No"):
            raise Exception(s)
        f = BytesIO(s.encode('ascii'))
        return Image.open(f, formats=['XBM'])

class EBhtml:

    TAG_RE = re.compile(r'^<([^>]+)>(.*)$')
    TEXT_RE = re.compile(r'^([^<]+)(.*)$')

    def __init__(self,
                 eblook: str=DEFAULT_EBLOOK,
                 estcmd: str=DEFAULT_ESTCMD,
                 global_alternate_ini: Path|None=GLOBAL_ALTERNATE_INI,
                 max_hits: int=DEFAULT_MAX_HITS):
        self.eb = EBlook(eblook, estcmd, global_alternate_ini, max_hits)
        self.gaiji_map: dict[str, str] = {}
        self.gaiji_cache: dict[str, str | None] = {}

    def close(self) -> None:
        self.eb.close()

    def __enter__(self) -> "EBhtml":
        return self

    def __exit__(self, exc_type: object, exc_value: object,
                 traceback: object) -> None:
        self.close()

    def set_book(
            self, path: Path, appendix: PathEx|None=None,
            alternate_ini: PathEx|None=None,
    ) -> EBLOOK_MENU:
        self.dictpath = path
        self.gaiji_cache = {}
        return self.eb.set_book(path, appendix, alternate_ini)

    def select_book(self,
                    num_or_tag: int|str,
                    gaiji_map: PathEx|None=None) -> list[str]:
        
        s = self.eb.select_book(num_or_tag)
        self.gaiji_cache = {}
        self.gaiji_map = {}
        if gaiji_map is None:
            gaiji_map = search_mapfile(self.dictpath, self.selected_book[1])
        if gaiji_map is not None and gaiji_map.exists():
            self.gaiji_map = read_mapfile(gaiji_map.get_path())
        return s

    @property
    def selected_book(self) -> tuple[int, str, str]:
        if self.eb.selected_book is None:
            raise Exception("Book is not selected yet")
        return self.eb.selected_book
    
    @property
    def supported_method(self) -> list[str]:
        return self.eb.supported_method
    
    @property
    def subbooks(self) -> EBLOOK_MENU:
        if self.eb.subbooks is None:
            raise Exception("Book is not opened yet")
        return self.eb.subbooks
    
    def search(self, word: str, method: str="glob",
               ignore_link: bool=True) -> str:
        result = ""
        list = self.eb.search(word, method)
        for num, ref, title in list:
            if len(result) != 0:
                result += '<hr />\n'
            result += '<h3>'
            result += self._eb2html(title)
            result += '</h3>\n'
            result += self._eb2html(self.eb.get_content(ref), ignore_link)
        return (f'<h2>Search {word}@{method} in {self.selected_book[2]}</h2>\n'
                + result)
    
    def _eb2html(self, s: str, ignore_link: bool=True) -> str:
        result = []
        last_href = []
        first_line = True
        in_ind = False
        font_stack = []

        for line in s.splitlines():
            if first_line:
                first_line = False
            elif not in_ind:
                result.append("<br />\n")
            if in_ind:
                result.append("</div>")
                in_ind = False

            while len(line) > 0:
                m = self.TAG_RE.match(line)
                if m:
                    tag = m.group(1)
                    line = m.group(2)

                    # indent
                    if tag.startswith("ind="):
                        if in_ind:
                            result.append("</div>")
                        indent = tag.split('=', 2)[1]
                        result.append(f'<div class="ind{indent}">')
                        in_ind = True

                    # image or inline-image
                    elif tag.startswith("img=") or tag.startswith("inline="):
                        # img_format: mono:WxH, jpeg, bmp
                        img_tag, img_format = tag.split('=', 2)
                        alt = ""
                        m2 = self.TEXT_RE.match(line)
                        if m2 is not None:
                            alt = m2.group(1).replace('"', "&quot;")
                            line = m2.group(2)

                        m2 = self.TAG_RE.match(line)
                        if m2 is None:
                            raise Exception(f'cannot found </{img_tag}> tag')
                        endtag = m2.group(1)
                        line = m2.group(2)
                        if not endtag.startswith(f'/{img_tag}='):
                            raise Exception(f"unkonw tag {endtag}")

                        ref = endtag.split('=', 2)[1]
                        if img_format in ("jpeg", "bmp"):
                            img_bin = self.eb.get_image(ref, format=img_format)
                        elif img_format.startswith("mono:"):
                            m3 = re.fullmatch(
                                r'mono:(\d+)[xX](\d+)', img_format)
                            if m3 is None:
                                raise Exception(
                                    f'unknow image format {img_format}')
                            img_bin = self.eb.get_mono_image(
                                ref, int(m3.group(1)), int(m3.group(2)))
                        else:
                            raise Exception(f'unknow image format {img_format}')

                        if isinstance(img_bin, bytes):
                            src = (
                                "data:image/jpeg;base64," +
                                base64.b64encode(img_bin).decode('ascii')
                            )
                        else:
                            with BytesIO() as f:
                                img_bin.save(f, 'png')
                                f.seek(0)
                                src = (
                                    "data:image/png;base64," +
                                    base64.b64encode(f.read()).decode('ascii')
                                )
                        if img_tag == "img":
                            result.append("<br />")
                        result.append(f'<img src="{src}" alt="{alt}">')
                        if img_tag == "img":
                            result.append("<br />")

                    # sound
                    elif tag.startswith("snd=") or tag == '/snd':
                        pass
                    # movie
                    elif tag.startswith("mov=") or tag == '/mov':
                        pass
                    
                    # bold/italic
                    elif tag.startswith("font="):
                        fonttype = tag.split('=', 2)[1]
                        font_stack.append(fonttype)
                        if fonttype == "bold":
                            result.append('<b>')
                        else:
                            result.append('<i>')
                    elif tag == "/font":
                        # eblook may emit a closing font tag without an
                        # opening one, so ignore stray closers.
                        if font_stack:
                            fonttype = font_stack.pop()
                            if fonttype == "bold":
                                result.append('</b>')
                            else:
                                result.append('</i>')
                    elif tag == "reference":
                        if not ignore_link:
                            last_href.append(len(result))
                            result.append("<a href=\"")
                    elif tag.startswith("/reference="):
                        if not ignore_link and last_href:
                            href = tag.split('=', 2)[1]
                            href_n = last_href.pop()
                            result[href_n] += href + '">'
                            result.append("</a>")
                    elif tag == "no-newline":
                        result.append('<span class="nobr">')
                    elif tag == "/no-newline":
                        result.append('</span>')
                    elif tag == "em":
                        result.append('<strong>')
                    elif tag == "/em":
                        result.append('</strong>')
                    elif tag in ("prev", "next", "sub", "/sub", "sup", "/sup"):
                        result.append(f"<{tag}>")
                    elif tag == "/prev":
                        self._truncate_to_marker(result, "<prev>")
                    elif tag == "/next":
                        self._truncate_to_marker(result, "<next>")
                    elif tag.startswith("gaiji="):
                        code = tag.split('=', 2)[1].lower()
                        if code in self.gaiji_map:
                            result.append(self.gaiji_map[code])
                        else:
                            if code in self.gaiji_cache:
                                img_data = self.gaiji_cache[code]
                            else:
                                img_data = None
                                try:
                                    img_bin = self.eb.get_font(code)
                                    with BytesIO() as f:
                                        img_bin.save(f, 'png')
                                        f.seek(0)
                                        img_data = (
                                            "data:image/png;base64," +
                                            base64.b64encode(
                                                f.read()).decode('ascii')
                                        )
                                except:
                                    pass
                                self.gaiji_cache[code] = img_data
                            alt = f"(外字:{code})"
                            if img_data is None:
                                result.append(alt)
                            else:
                                result.append(
                                    f'<img src="{img_data}" alt="{alt}" />')
                    else:
                        raise Exception(f"unknown tag {tag}")
                else:
                    m = self.TEXT_RE.match(line)
                    if m:
                        result.append(m.group(1))
                        line = m.group(2)
                    else:
                        # neither a tag nor text (e.g. a lone '<'): emit it
                        # as is so that the loop always makes progress
                        result.append(line)
                        line = ""
        if in_ind:
            result.append("</div>")
        return "".join(result)

    @staticmethod
    def _truncate_to_marker(result: list[str], marker: str) -> None:
        """Drop marker and everything appended after it."""
        for i in range(len(result) - 1, -1, -1):
            if result[i] == marker:
                del result[i:]
                return
