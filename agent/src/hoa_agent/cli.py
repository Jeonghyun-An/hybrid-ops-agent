import argparse
from collections.abc import Sequence

from hoa_agent import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hoa", description="hybrid-ops-agent 명령줄 도구")
    parser.add_argument("--version", action="version", version=f"hoa {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0
