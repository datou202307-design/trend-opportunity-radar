from __future__ import annotations

import time
from typing import Any, Callable


POLICY_VERSION = "controlled-read-pacing-v0.1"
MAX_PARALLEL_READS = 1
BATCH_SIZE = 5
DEFAULT_BATCH_COOLDOWN_SECONDS = 30
RATE_LIMIT_COOLDOWN_SECONDS = 30 * 60
PLATFORM_INTERVALS: dict[str, dict[str, int]] = {
    "x": {"search": 10, "detail": 10, "comment": 10},
    "xiaohongshu": {"search": 15, "detail": 20, "comment": 20},
    "youtube": {"search": 10, "detail": 10, "comment": 10},
    "tiktok": {"search": 12, "detail": 12, "comment": 12},
}


def pacing_policy(platform: str, action: str) -> dict[str, Any]:
    platform_key = str(platform or "").casefold()
    action_key = str(action or "search").casefold()
    interval = PLATFORM_INTERVALS.get(platform_key, {}).get(action_key, 10)
    cooldown = 45 if platform_key == "xiaohongshu" else DEFAULT_BATCH_COOLDOWN_SECONDS
    return {
        "policy_version": POLICY_VERSION,
        "platform": platform_key,
        "action": action_key,
        "max_parallel_reads": MAX_PARALLEL_READS,
        "interval_seconds": interval,
        "batch_size": BATCH_SIZE,
        "batch_cooldown_seconds": cooldown,
        "randomized": False,
    }


def throttle_before_read(
    platform: str,
    action: str,
    request_index: int,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Apply a transparent, deterministic, serialized browser-read cadence."""
    policy = pacing_policy(platform, action)
    cooldown = policy["batch_cooldown_seconds"] if request_index > 0 and request_index % policy["batch_size"] == 0 else 0
    waited = 0 if request_index <= 0 else policy["interval_seconds"] + cooldown
    if waited:
        sleeper(waited)
    return {
        **policy,
        "request_index": request_index,
        "applied_batch_cooldown_seconds": cooldown,
        "waited_seconds": waited,
    }
