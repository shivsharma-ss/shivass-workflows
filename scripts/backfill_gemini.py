"""CLI utility to backfill Gemini analyses for stored YouTube videos."""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Optional

from app.config import Settings
from services.container import AppContainer

logger = logging.getLogger(__name__)


async def _run_backfill(
    batch_size: int,
    resume_after: Optional[str],
    dry_run: bool,
) -> int:
    settings = Settings()
    container = AppContainer(settings)
    await container.startup()

    if not container.gemini:
        logger.error("Gemini API key is not configured; aborting.")
        return 1

    storage = container.storage
    gemini = container.gemini

    processed = 0
    resume_token = resume_after

    while True:
        rows = await storage.list_videos_missing_analysis(limit=batch_size, resume_after=resume_token)
        if not rows:
            break
        for row in rows:
            video_id = row["video_id"]
            url = row["url"]
            if dry_run:
                logger.info("[dry-run] would analyze %s", url)
            else:
                try:
                    analysis = await gemini.analyze_video(url)
                except Exception:
                    logger.exception("Gemini analysis failed for %s", url)
                    continue
                if analysis:
                    logger.info("Backfilled %s", url)
                else:
                    logger.warning("Gemini returned no analysis for %s", url)
            processed += 1
            resume_token = video_id
        if dry_run:
            break

    logger.info(
        "Completed backfill: processed %s video(s)%s",
        processed,
        " [dry-run]" if dry_run else "",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Gemini analyses into SQLite.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of videos to fetch per batch (default: 25, max: 500).",
    )
    parser.add_argument(
        "--resume-after",
        type=str,
        default=None,
        help="Video ID to resume after (exclusive).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the videos that would be processed without calling Gemini.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ...).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )

    batch_size = max(1, min(args.batch_size, 500))
    return asyncio.run(_run_backfill(batch_size, args.resume_after, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
