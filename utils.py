from datetime import timedelta, datetime
import random


def randomize_timedelta(td: timedelta, spread: float = 0.25) -> timedelta:
    seconds = td.total_seconds()
    randomized_seconds = random.uniform(seconds * (1 - spread), seconds * (1 + spread))
    return timedelta(seconds=randomized_seconds)


def get_chance(probability: float) -> bool:
    return random.random() < probability

def clamp_datetime(dt: datetime, start: datetime, end: datetime) -> datetime:
    if dt < start:
        return start
    if dt > end:
        return end
    return dt

def generate_publish_times(start_dt: datetime, end_dt: datetime, post_count: int,
                           jitter_spread: float = 0.15, min_margin: timedelta | None = None) -> list[datetime]:
    if post_count <= 0:
        return []

    if min_margin is None:
        min_margin = timedelta(seconds=1)

    total = end_dt - start_dt
    if total <= min_margin * 2:
        return []

    eff_start = start_dt + min_margin
    eff_end = end_dt - min_margin
    eff_total = eff_end - eff_start

    slot = eff_total / (post_count + 1)

    result = []
    for i in range(post_count):
        base = eff_start + slot * (i + 1)
        jitter_seconds = (random.random() * 2 - 1) * slot.total_seconds() * jitter_spread
        dt = base + timedelta(seconds=jitter_seconds)
        dt = clamp_datetime(dt, eff_start, eff_end)
        result.append(dt)

    result.sort()
    return result
