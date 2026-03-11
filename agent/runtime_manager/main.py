from __future__ import annotations

import argparse

from agent.runtime_manager.worker import RuntimeManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Urban Insight agent runtime manager")
    parser.add_argument("--once", action="store_true", help="Process at most one claimed run and exit")
    args = parser.parse_args()

    manager = RuntimeManager()
    if args.once:
        try:
            manager.run_once()
        finally:
            manager.close()
        return

    manager.run_forever()


if __name__ == "__main__":
    main()
