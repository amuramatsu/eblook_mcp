#! /usr/bin/env python3
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

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from . import config as config_module
from . import log as log_module

# __name__ is "__main__" when run with `python -m eblook_mcp`, so use an
# explicit child logger to stay under the package logger configured by
# log.setup_logging().
LOGGER = logging.getLogger(f"{log_module.LOGGER_NAME}.__main__")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eblook-mcp",
        description="MCP server that provides dictionary services via eblook")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--config", metavar="FILE", type=Path,
        help="config file to use "
             f"(default: {config_module.default_config_path()})")
    group.add_argument(
        "--gen-config", metavar="DIR", type=Path,
        help="generate config.toml from the dictionaries under DIR "
             "and print it to stdout")
    parser.add_argument(
        "--loglevel", nargs="?", const=None, type=str.lower,
        choices=list(log_module.LOG_LEVELS), metavar="LEVEL",
        help="write a log file at LEVEL (debug/info/warning/error); "
             "no log is written without an explicit LEVEL")
    parser.add_argument(
        "--logfile", metavar="FILE",
        help="log file path used with --loglevel LEVEL; "
             "%%Y %%M %%D %%H %%m %%s are replaced with the current time "
             "(default: next to config.toml, %%Y_%%M_%%D.log)")
    return parser


def configure_logging(args: argparse.Namespace) -> bool:
    """Set up file logging when --loglevel LEVEL was given."""
    if args.loglevel is None:
        return True
    level = args.loglevel
    if args.logfile is not None:
        path = log_module.expand_logfile(args.logfile)
    else:
        config_path = (
            args.config if args.config is not None
            else config_module.default_config_path())
        path = log_module.default_logfile(config_path)
    try:
        logger = log_module.setup_logging(level, path)
    except OSError as e:
        print(f"eblook-mcp: cannot open log file: {e}", file=sys.stderr)
        return False
    logger.info("logging started (level=%s)", level)
    return True


def run_server(cfg: config_module.Config) -> int:
    try:
        from .mcp_server import create_server
    except ModuleNotFoundError as e:
        if e.name == "fastmcp" or (e.name and e.name.startswith("fastmcp.")):
            LOGGER.error(
                "FastMCP is not installed; run `pip install -e .` first")
            return 2
        raise
    try:
        server = create_server(cfg)
        server.run(transport="stdio")
    except Exception:
        LOGGER.exception("server stopped unexpectedly")
        return 1
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.logfile is not None and args.loglevel is None:
        parser.error("--logfile requires --loglevel LEVEL")
    if not configure_logging(args):
        return 2

    if args.gen_config is not None:
        try:
            print(config_module.generate_config(args.gen_config))
        except (OSError, ValueError) as e:
            LOGGER.error("%s", e)
            return 2
        return 0

    try:
        cfg = config_module.load_config(args.config)
    except (OSError, ValueError) as e:
        LOGGER.error("%s", e)
        return 2
    return run_server(cfg)


if __name__ == "__main__":
    sys.exit(main())
