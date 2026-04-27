from __future__ import annotations

from datetime import date
from typing import Iterable, List

from tqdm import tqdm

from .cache import CacheProvider
from .cache_keys import build_cache_key
from .models import HoroscopeRequest, Period, Section, ZODIAC_SIGNS
from .service import HoroscopeService


def ttl_for_period(period: Period) -> int:
    if period == Period.DAILY:
        return 60 * 60 * 24
    if period == Period.WEEKLY:
        return 60 * 60 * 24 * 7
    if period == Period.MONTHLY:
        return 60 * 60 * 24 * 32
    if period == Period.YEARLY:
        return 60 * 60 * 24 * 370
    return 60 * 60 * 6


def pregenerate(
    service: HoroscopeService,
    cache: CacheProvider,
    period: Period,
    target_date: date,
    signs: Iterable[str] = ZODIAC_SIGNS,
    sections: List[Section] | None = None,
    tenant_id: str | None = None,
    progress: bool = True,
) -> int:
    sign_list = list(signs)
    iterator = (
        tqdm(sign_list, desc="Pregenerating", unit="sign") if progress else sign_list
    )
    total = 0
    for sign in iterator:
        request = HoroscopeRequest(
            period=period,
            sign=sign,
            target_date=target_date,
            sections=sections,
        )
        response = service.generate(request)
        cache_key = build_cache_key(
            tenant_id=tenant_id,
            period=period,
            sign=sign,
            sign_source="provided",
            sections=[section.value for section in sections] if sections else None,
            target_date=target_date,
            birth_date=None,
            birth_time=None,
            birth_latitude=None,
            birth_longitude=None,
            birth_timezone=None,
            zodiac_system=None,
            ayanamsa=None,
            house_system=None,
            node_type=None,
        )
        cache.set(
            cache_key, response.model_dump_json(), ttl_seconds=ttl_for_period(period)
        )
        total += 1
    return total
