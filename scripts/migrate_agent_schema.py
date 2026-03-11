import sys
from pathlib import Path

from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.models import AGENT_TABLE_NAMES
from backend.database import engine, init_db


def main() -> None:
    before = set(inspect(engine).get_table_names())
    init_db()
    after = set(inspect(engine).get_table_names())

    created = sorted(name for name in AGENT_TABLE_NAMES if name in after and name not in before)
    existing = sorted(name for name in AGENT_TABLE_NAMES if name in after and name in before)
    missing = sorted(name for name in AGENT_TABLE_NAMES if name not in after)

    print("Agent schema initialization complete.")
    print(f"Database URL: {engine.url}")
    print(f"Agent tables present: {len(existing) + len(created)}/{len(AGENT_TABLE_NAMES)}")

    if created:
        print("Created tables:")
        for name in created:
            print(f"  - {name}")

    if existing:
        print("Already existed:")
        for name in existing:
            print(f"  - {name}")

    if missing:
        print("Missing tables:")
        for name in missing:
            print(f"  - {name}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
