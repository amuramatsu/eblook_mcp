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

import logging
import os
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import eblook
from .common import PathEx, DEFAULT_EBLOOK, DEFAULT_ESTCMD, DEFAULT_MAX_HITS

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef, import-not-found]

LOGGER = logging.getLogger(__name__)

CONFIG_DIR_NAME = "eblook_mcp"
CONFIG_FILE_NAME = "config.toml"
ALTERNATE_INI_NAME = "alternate.ini"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / CONFIG_DIR_NAME


def default_config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


def default_alternate_ini_path() -> Path:
    return config_dir() / ALTERNATE_INI_NAME


def search_dictionary(dictpath: Path) -> dict[str, dict[str, Any]]:
    if not dictpath.is_dir():
        raise ValueError(f"not a directory: {dictpath}")
    result: dict[str, dict[str, Any]] = {}
    with eblook.EBlook() as eb:
        for d in sorted(dictpath.glob('*')):
            if not d.is_dir():
                continue
            if d.name.startswith('.'):
                continue
            try:
                books = eb.set_book(d)
                bundle_name = d.name
                appendix_path = eblook.search_appendix(d)
                alternate_path = eblook.search_alternate_ini(d)
                for num, subbook, title in books:
                    method = eb.select_book(num)
                    mapfile_path = eblook.search_mapfile(d, subbook)
                    title = unicodedata.normalize('NFKC', title)
                    title = title.replace('’', "'")
                    result[f'{bundle_name}:{subbook}'] = {
                        "title": title,
                        "description": "",
                        "path": str(d.absolute()),
                        "subbook": subbook,
                        "appendix": "" if appendix_path.is_empty() else (
                            appendix_path.abs_str()),
                        "alternate_ini": "" if alternate_path.is_empty() else (
                            alternate_path.abs_str()),
                        "mapfile": "" if mapfile_path.is_empty() else (
                            mapfile_path.abs_str()),
                        "method": method,
                    }
            except Exception as e:
                LOGGER.warning("%s: %s", d, e)
    return result


def _toml_str(value: str) -> str:
    out = []
    for ch in value:
        if ch == '\\':
            out.append('\\\\')
        elif ch == '"':
            out.append('\\"')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif ord(ch) < 0x20:
            out.append(f'\\u{ord(ch):04x}')
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def generate_config(
        dictpath: Path,
        eblook_path: str = "",
        estcmd_path: str = "",
) -> str:
    dictionaries = search_dictionary(dictpath)
    lines = [
        "# eblook_mcp configuration",
        f"# generated from: {dictpath}",
        "#",
        "# Relative paths are resolved against the directory of this file.",
        "#",
        "# An empty eblook/estcmd value means: find the command in PATH.",
        f"eblook = {_toml_str(eblook_path)}",
        f"estcmd = {_toml_str(estcmd_path)}",
        "#",
        "# Maximum number of hits per search (0 means unlimited).",
        f"max_hits = {DEFAULT_MAX_HITS}",
        "#",
        f"# Global alternate.ini (default: {default_alternate_ini_path()})",
        "# Omit the key to use the default when the file exists,",
        '# set it to "" to disable it, or to a path to override it.',
        f"# alternate_ini = {default_alternate_ini_path()}",
        "",
    ]
    for key in sorted(dictionaries):
        d = dictionaries[key]
        lines += [
            f'[[dictionaries.{_toml_str(key)}]]',
            f'path = {_toml_str(d["path"])}',
            f'subbook = {_toml_str(d["subbook"])}',
            f'title = {_toml_str(d["title"])}',
            f'description = {_toml_str(d["description"])}',
            f'appendix = {_toml_str(d["appendix"])}',
            f'alternate_ini = {_toml_str(d["alternate_ini"])}',
            f'mapfile = {_toml_str(d["mapfile"])}',
            "",
        ]
    return "\n".join(lines)


def _resolve_path(value: str, base: "Path | None") -> Path:
    p = Path(value)
    if base is not None and not p.is_absolute():
        p = base / p
    return Path(os.path.normpath(p))


def _resolve_command(value: str, base: "Path | None") -> str:
    """Resolve a command path; keep bare command names untouched."""
    if value == "":
        return ""
    if os.sep in value or (os.altsep is not None and os.altsep in value):
        return str(_resolve_path(value, base))
    return value


def _optional_path(
        name: str, entry: dict[str, Any], key: str,
        base: Path|None= None) -> PathEx|None:
    """Convert an optional path setting into the PathEx three-state.

    The key is absent  -> None (not defined yet, search file automatically)
    The value is empty -> PathEx(None) (set to nothing: unused this file)
    Otherwise          -> PathEx(Path(value))

    A relative path is resolved against the config file directory.
    """
    if key not in entry:
        return None
    value = entry[key]
    if not isinstance(value, str):
        raise ValueError(f"dictionaries.{name}.{key} must be a string")
    if value == "":
        return PathEx(None)
    return PathEx(_resolve_path(value, base))


@dataclass
class Dictionary:
    name: str
    path: Path
    subbook: str
    title: str = ""
    description: str = ""
    appendix: PathEx|None = None
    alternate_ini: PathEx|None = None
    mapfile: PathEx|None = None


@dataclass
class Config:
    path: Path|None = None
    eblook_cmd: str = DEFAULT_EBLOOK
    estcmd_cmd: str = DEFAULT_ESTCMD
    alternate_ini: Path|None = None
    max_hits: int = DEFAULT_MAX_HITS
    dictionaries: dict[str, Dictionary] = field(default_factory=dict)

    def new_eblook(self) -> eblook.EBlook:
        return eblook.EBlook(
            self.eblook_cmd, self.estcmd_cmd, self.alternate_ini,
            self.max_hits)


def _parse_dictionary(
        name: str, entry: dict[str, Any], base: Path|None) -> Dictionary:
    if not isinstance(entry, dict):
        raise ValueError(f"dictionaries.{name} must be a table")
    if "path" not in entry:
        raise ValueError(f"dictionaries.{name}: missing 'path'")
    if "subbook" not in entry:
        raise ValueError(f"dictionaries.{name}: missing 'subbook'")
    return Dictionary(
        name=name,
        path=_resolve_path(str(entry["path"]), base),
        subbook=str(entry["subbook"]),
        title=str(entry.get("title", "")),
        description=str(entry.get("description", "")),
        appendix=_optional_path(name, entry, "appendix", base),
        alternate_ini=_optional_path(name, entry, "alternate_ini", base),
        mapfile=_optional_path(name, entry, "mapfile", base),
    )


def parse_config(
        data: dict[str, Any], path: Path|None=None) -> Config:
    base = path.parent if path is not None else None
    cfg = Config(path=path)
    cfg.eblook_cmd = (
        _resolve_command(str(data.get("eblook", "")), base)
        or DEFAULT_EBLOOK)
    cfg.estcmd_cmd = (
        _resolve_command(str(data.get("estcmd", "")), base)
        or DEFAULT_ESTCMD)

    max_hits = data.get("max_hits", DEFAULT_MAX_HITS)
    if isinstance(max_hits, bool) or not isinstance(max_hits, int):
        raise ValueError("max_hits must be an integer")
    if max_hits < 0:
        raise ValueError("max_hits must be >= 0")
    cfg.max_hits = max_hits

    if "alternate_ini" in data:
        value = data["alternate_ini"]
        if not isinstance(value, str):
            raise ValueError("alternate_ini must be a string")
        if value != "":
            alt = _resolve_path(value, base)
            if alt.exists():
                cfg.alternate_ini = alt
            else:
                LOGGER.warning("alternate.ini not found: %s", alt)
    else:
        alt = default_alternate_ini_path()
        if alt.exists():
            cfg.alternate_ini = alt

    raw = data.get("dictionaries", {})
    if not isinstance(raw, dict):
        raise ValueError("dictionaries must be a table")
    for name, value in raw.items():
        entries = value if isinstance(value, list) else [value]
        if len(entries) != 1:
            raise ValueError(
                f"dictionaries.{name}: expected one table, got {len(entries)}")
        cfg.dictionaries[name] = _parse_dictionary(name, entries[0], base)
    return cfg


def load_config(path: Path|str|None=None) -> Config:
    config_path = Path(path) if path is not None else default_config_path()
    if not config_path.is_file():
        raise FileNotFoundError(f"config file not found: {config_path}")
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return parse_config(data, config_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            f"usage: python -m {__package__ or 'eblook_mcp'}.config DICT_DIR",
            file=sys.stderr)
        raise SystemExit(2)
    print(generate_config(Path(sys.argv[1])), end="")
