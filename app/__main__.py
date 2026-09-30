"""Command line entry point.

    python -m app serve            # web app + daily scheduler
    python -m app build            # build today's briefing now
    python -m app setup            # download the Kokoro voice model
"""
from __future__ import annotations

import argparse
import logging
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app", description="Morning Brief news app")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the web app and daily scheduler")
    serve.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    sub.add_parser("build", help="build today's briefing now")
    sub.add_parser("setup", help="download the Kokoro voice model (~350 MB)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("app.main:factory", factory=True, host=args.host, port=args.port)
    elif args.cmd == "build":
        from .briefing import build_briefing
        from .config import load
        from .db import Database

        cfg = load()
        briefing = build_briefing(cfg, Database(cfg.db_path))
        print(f"Built {briefing['title']}: {len(briefing['stories'])} stories, "
              f"{briefing['duration'] / 60:.1f} min, voice {briefing['voice']['name']}, writer {briefing['writer']}")
    elif args.cmd == "setup":
        from .config import load
        from .tts.kokoro import download_models

        cfg = load()
        last = {}

        def progress(name: str, done: int, total: int) -> None:
            pct = done * 100 // total
            if last.get(name) != pct and pct % 10 == 0:
                last[name] = pct
                print(f"  {name}: {pct}%")

        download_models(cfg.model_dir, progress)
        print(f"Voice model ready in {cfg.model_dir}")


if __name__ == "__main__":
    main()
