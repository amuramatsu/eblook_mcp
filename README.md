# eblook MCP server

An MCP server that provides EPWING dictionary search services through
[eblook](https://ikazuhiro.s206.xrea.com/staticpages/index.php/eblook).
It is built with [FastMCP](https://github.com/jlowin/fastmcp) and exposes
dictionary listing, dictionary selection, and HTML search results as MCP tools.

## Features

| Tool | Description |
|---|---|
| `list_dictionaries` | List the configured dictionaries with their tags and descriptions. |
| `set_dictionary` | Select the dictionary to search; returns supported search methods and a search-query guide. |
| `search` | Search the selected dictionary and return the entries as HTML. |
| `search_multiple` | Search several dictionaries with one word and return one combined HTML document. |

Search results are HTML fragments. The heading contains the search word, the
search method, and the dictionary title, for example
`Search 楽器@glob in 広辞苑第六版`.

## Requirements

- Python 3.10 or later
- The `eblook` command on `PATH` (see the
  [eblook project page](https://ikazuhiro.s206.xrea.com/staticpages/index.php/eblook))
- EPWING dictionary data
- `estcmd` on `PATH` **only** for full-text search. A dictionary must also
  contain an `_ebest` index, created as described in
  [Making an ebest index](http://green.ribbon.to/~ikazuhiro/dic/ebestmk.html).

## Installation

End-user installation with [pipx](https://pipx.pypa.io/):

```console
make install
# equivalent to: pipx install --force .
```

This installs the `eblook-mcp` command into an isolated environment.

For development:

```console
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
make test
```

## Configuration

The default config file is `${XDG_CONFIG_HOME}/eblook_mcp/config.toml`
(`~/.config/eblook_mcp/config.toml` when `XDG_CONFIG_HOME` is unset).

Generate an initial config from a directory containing dictionaries:

```console
eblook-mcp --gen-config /usr/local/share/dict > \
    "${XDG_CONFIG_HOME:-$HOME/.config}/eblook_mcp/config.toml"
```

Example config:

```toml
eblook = ""
estcmd = ""
max_hits = 25

[[dictionaries."koujien:kojien"]]
path = "/usr/local/share/dict/koujien"
subbook = "kojien"
title = "広辞苑 第六版"
description = "Japanese word dictionary"
mapfile = "/usr/local/share/dict/koujien/kojien.map"
appendix = ""
alternate_ini = ""
```

Top-level keys:

| Key | Default | Description |
|---|---|---|
| `eblook` | `""` | Path to `eblook`; empty means look it up on `PATH`. |
| `estcmd` | `""` | Path to `estcmd`; empty means look it up on `PATH`. |
| `max_hits` | `25` | Maximum number of hits per search; `0` means unlimited. |
| `alternate_ini` | unset | Global alternate character map. When unset, the default path is used if it exists; `""` disables it. |

Relative paths are resolved against the directory of the config file.
`eblook` and `estcmd` values without `/` are treated as command names and
looked up on `PATH`.

Each dictionary is an entry such as `[[dictionaries."NAME:SUBBOOK"]]` (quotes
are required because TOML bare keys cannot contain `:`). `path` and `subbook`
are required; `title` and `description` are optional display strings. `subbook`
is the subbook name reported by eblook's `list` command (lowercase).

`appendix`, `alternate_ini`, and `mapfile` each have three states:

- key absent: auto-detect (`_appendix`, `alternate.ini`, `SUBBOOK.map`)
- empty string: explicitly disabled
- a path: use that path

## Command-line usage

| Invocation | Behavior |
|---|---|
| `eblook-mcp` | Read the default config and start the MCP server over stdio. |
| `eblook-mcp --config FILE` | Start the server with the specified config file (exclusive with `--gen-config`). |
| `eblook-mcp --gen-config DIR` | Generate a config from dictionaries under `DIR` and print it to stdout. |
| `eblook-mcp --loglevel LEVEL` | Write a log file at `LEVEL` (`debug`, `info`, `warning`, or `error`). No log is written when `LEVEL` is omitted. |
| `eblook-mcp --logfile FILE` | Write the log to `FILE` together with `--loglevel LEVEL`; using it without a level is a parse error. `%Y`, `%M`, `%D`, `%H`, `%m`, and `%s` are replaced with the year, month, day, hour, minute, and second. |
| `eblook-mcp --version` | Print the version. |

Logging uses Python's standard `logging` module and always writes to a file,
never to stdout, because stdout carries the MCP protocol over stdio. Logging is
enabled only by an explicit `--loglevel LEVEL`; `--logfile` requires a level
and is rejected on its own. The default log file is `%Y_%M_%D.log` in the
directory of the config file. Errors
that stop the command (bad config, failed config generation, an unexpected
server failure) and exceptions raised by MCP tools are logged as errors, with a
traceback where available.

A typical MCP client configuration for stdio:

```json
{
  "mcpServers": {
    "eblook-mcp": {
      "command": "eblook-mcp",
      "args": ["--config", "/path/to/config.toml"]
    }
  }
}
```

## MCP tools in detail

1. `list_dictionaries()` returns the `tag`, `title`, and `description` of every
   configured dictionary.
2. `set_dictionary(tag)` selects a dictionary. Pass a `tag` returned by
   `list_dictionaries` (`NAME:SUBBOOK`); a bare subbook name is not accepted.
   The result contains `supported_methods` and `search_query_guide`, which
   explains how to write search queries for each method.
3. `search(word, method="glob")` searches the selected dictionary and returns
   HTML. Call `set_dictionary` first.
4. `search_multiple(tags, word, method="glob")` applies one query to all given
   dictionaries and returns the results as a single HTML document. The current
   dictionary selection is left unchanged.

The dictionary selection is kept per server session. All eblook operations are
serialized because a single eblook subprocess is used.

Full-text search (`method="fulltext"`) requires an index generated with
[ebestmk](http://green.ribbon.to/~ikazuhiro/dic/ebestmk.html) in addition to
`estcmd`; without it, the method is not listed by `set_dictionary`.

## Development

| Make target | Description |
|---|---|
| `make install` | Install the `eblook-mcp` command with pipx. |
| `make build` | Build a wheel into `dist/` using `.venv`. |
| `make typecheck` | Run `mypy --strict` on the `eblook_mcp` package and `tests`. |
| `make test` | Run `mypy --strict` and then the test suite with `.venv`'s pytest. |
| `make coverage` | Run the tests with line coverage of the `eblook_mcp` package. |
| `make clean` | Remove `.venv`, `dist/`, and other build artifacts. |

Tests live in `tests/`. They import the package from the editable install made
by `make test`, so run them through the project virtualenv rather than the
system Python. `make test` runs a strict type check on both the package and the
tests first, so a type error fails the test target before pytest starts. Tests
that need real dictionaries are marked `integration` and use
`EBLOOK_DICT_ROOT` (default `/usr/local/share/dict`); they are skipped when the
dictionaries are unavailable. To run only the fast tests, use
`.venv/bin/python -m pytest -m "not integration"`. For a visual check of
generated HTML, run `python tests/manual_eblook.py 2`.

## Reference

- [eblook](https://ikazuhiro.s206.xrea.com/staticpages/index.php/eblook)
- [FastMCP](https://github.com/jlowin/fastmcp)
