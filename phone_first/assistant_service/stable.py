from __future__ import annotations

import sys

from assistant_service.agent import run


def main() -> None:
    sys.argv = [sys.argv[0], "start", *sys.argv[1:]]
    run()


if __name__ == "__main__":
    main()
