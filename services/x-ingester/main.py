"""
X/Twitter ingester — polls configured accounts via Twscrape.

First-time account setup:
    docker compose run --rm -it x-ingester python -m twscrape add_accounts
    docker compose run --rm -it x-ingester python -m twscrape login_accounts

Then run normally:
    docker compose up x-ingester
"""

import asyncio
import logging
from datetime import timezone

import twscrape

from config import settings
from db import get_active_x_sources, insert_message
from pubsub import publish_raw_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [x] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

STANDBY_POLL_INTERVAL = 60


async def poll_account(
    api: twscrape.API,
    source: dict,
    last_seen_ids: dict[str, int],
) -> None:
    handle = source["identifier"]
    source_id = source["id"]
    last_id = last_seen_ids.get(handle, 0)

    try:
        tweets = []
        async for tweet in api.user_tweets(handle, limit=20):
            if tweet.id <= last_id:
                break
            tweets.append(tweet)
    except Exception as e:
        log.error("Failed to fetch tweets for @%s: %s", handle, e)
        return

    for tweet in reversed(tweets):
        raw_json = {
            "source": "x",
            "author": handle,
            "text": tweet.rawContent,
            "timestamp": tweet.date.isoformat(),
            "tweet_id": tweet.id,
            "is_retweet": tweet.retweetedTweet is not None,
            "is_reply": tweet.inReplyToTweetId is not None,
            "like_count": tweet.likeCount,
            "retweet_count": tweet.retweetCount,
        }

        has_media = bool(tweet.media and (tweet.media.photos or tweet.media.videos))
        ts = tweet.date.replace(tzinfo=timezone.utc) if tweet.date.tzinfo is None else tweet.date

        msg_id = await insert_message(
            source_id=source_id,
            external_id=str(tweet.id),
            text=tweet.rawContent or "",
            raw_json=raw_json,
            has_media=has_media,
            timestamp=ts,
        )

        if msg_id:
            raw_json["db_id"] = msg_id
            await publish_raw_message(raw_json)
            log.info("Ingested msg %d from @%s (tweet %d)", msg_id, handle, tweet.id)

    if tweets:
        last_seen_ids[handle] = max(t.id for t in tweets)


async def run_ingester(api: twscrape.API) -> None:
    sources = await get_active_x_sources()

    if not sources:
        log.warning("No active X sources in database. Add entries to sources table.")
        log.info("Entering standby — rechecking every %ds.", STANDBY_POLL_INTERVAL)
        while True:
            await asyncio.sleep(STANDBY_POLL_INTERVAL)
            sources = await get_active_x_sources()
            if sources:
                log.info("Sources found, starting poll loop.")
                break

    handles = [s["identifier"] for s in sources]
    log.info("Polling %d account(s): %s", len(handles), handles)

    last_seen_ids: dict[str, int] = {}

    while True:
        for source in sources:
            await poll_account(api, source, last_seen_ids)

        log.info("Poll cycle complete. Sleeping %ds.", settings.x_poll_interval)
        await asyncio.sleep(settings.x_poll_interval)

        # Reload sources each cycle to pick up config changes
        sources = await get_active_x_sources()


async def main() -> None:
    api = twscrape.API(settings.x_accounts_db_path)

    try:
        await run_ingester(api)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.exception("Unhandled error: %s", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
