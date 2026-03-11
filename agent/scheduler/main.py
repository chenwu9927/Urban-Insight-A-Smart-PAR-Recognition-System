from __future__ import annotations

import argparse

from agent.scheduler.worker import AgentScheduler


def main() -> None:
    parser = argparse.ArgumentParser(description="Urban Insight agent scheduler")
    parser.add_argument("--once", action="store_true", help="Dispatch due tasks once and exit")
    args = parser.parse_args()

    scheduler = AgentScheduler()
    if args.once:
        try:
            scheduler.run_once()
        finally:
            scheduler.close()
        return

    scheduler.run_forever()


if __name__ == "__main__":
    main()
