"""Server für den Oberflächentest (Playwright): eingerichtete Arena gegen die Nachbauten.

    uv run python -m tests.e2e_server [--port 8399]

Legt einen frischen Datenordner an, startet die nachgebaute Plattform und die App. Kein Netz, kein
BW-System, keine Schlüssel.
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8399)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="aiarena4bw-e2e-"))
    os.environ["AIARENA_DATA_DIR"] = str(root / "data")
    os.environ["AIARENA_TASKS_DIR"] = str(root / "tasks")
    os.environ["AIARENA_KEYRING"] = "off"

    import uvicorn

    from aiarena4bw import db, vault
    from aiarena4bw.api import create_app

    from .fakes.fake_platform import FakePlatform
    from .fakes.seed import seed

    platform = FakePlatform()
    conn = db.connect()
    seed(conn, platform.url, root / "bw-state.json", root / "tasks",
         lambda name, value: os.environ.__setitem__(vault.env_name(name), value))  # fmt: skip
    conn.execute("DELETE FROM meta WHERE key='notice_accepted'")  # Der Oberflächentest bestätigt selbst.
    conn.close()
    try:
        uvicorn.run(create_app(port=args.port), host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        platform.close()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
