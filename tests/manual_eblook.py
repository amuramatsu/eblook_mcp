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

"""Dump HTML for a dictionary by hand.

Usage:
    python tests/manual_eblook.py [1|2|3|4]

1: GENIUS_DAIEIWA 'find*'
2: koujien '楽器'
3: scitech_EJ-JE 'pearl' (fulltext)
4: GENIUS_DAIEIWA 'Gödel'
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eblook_mcp.eblook import CSS_TEXT, EBhtml

DICT_ROOT = Path(os.environ.get("EBLOOK_DICT_ROOT", "/usr/local/share/dict"))


def dump(name: str, word: str, method: str = "glob") -> None:
    with EBhtml() as ebh:
        ebh.set_book(DICT_ROOT / name)
        ebh.select_book(1)
        print(ebh.search(word, method=method))


CASES = {
    "1": ("GENIUS_DAIEIWA", "find*", "glob"),
    "2": ("koujien", "楽器", "glob"),
    "3": ("scitech_EJ-JE", "pearl", "fulltext"),
    "4": ("GENIUS_DAIEIWA", "Gödel", "glob"),
}


def main(argv: list[str]) -> int:
    key = argv[1] if len(argv) > 1 else "1"
    if key not in CASES:
        print(f"usage: {argv[0]} [{'|'.join(sorted(CASES))}]", file=sys.stderr)
        return 2
    print('<html><head><meta charset="utf-8" />'
          f'<style>{CSS_TEXT}</style></head><body>')
    dump(*CASES[key])
    print("</body></html>")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
