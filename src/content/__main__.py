"""The `content` command: a topic makes a video (`cli/run.py`); a named command runs one of
the tools (`content <command> --help`)."""

import sys
from collections.abc import Callable

from dotenv import load_dotenv

from content.cli import channel, learning, review, run, storage

COMMANDS: dict[str, Callable[[list[str]], int]] = {
    **review.COMMANDS,
    **channel.COMMANDS,
    **learning.COMMANDS,
    **storage.COMMANDS,
}


def main() -> int:
    load_dotenv()
    if sys.argv[1:2] and sys.argv[1] in COMMANDS:
        return COMMANDS[sys.argv[1]](sys.argv[2:])
    return run.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
