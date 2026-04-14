from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import Response, JSONResponse

from .cache import cache_from_env
from .cache_keys import build_cache_key
from .config import ServiceConfig
from .healthcheck import run_content_coverage_healthcheck
from .models import (
    BirthdayHoroscopeRequest,
    HoroscopeRequest,
    HoroscopeResponse,
    NatalBirthchartRequest,
    NatalBirthchartResponse,
    Period,
    PlanetHoroscopeRequest,
    PregenRequest,
)
from .natal_artifacts import (
    build_natal_report_pdf,
    build_natal_wheel_png,
    build_natal_wheel_svg,
    build_house_overlay_map,
)
from .observability import MetricsCollector, Timer
from .pregen import pregenerate
from .service import HoroscopeService
from .versioning import resolve_version


logger = logging.getLogger(__name__)

service_config = ServiceConfig()
service = HoroscopeService(service_config)
cache = cache_from_env(service_config.cache_ttl_seconds)
metrics = MetricsCollector()


def _run_startup_content_healthcheck() -> None:
    if os.getenv("CONTENT_HEALTHCHECK_DISABLE", "0") == "1":
        return
    if service.content_repository is None:
        logger.info("content-healthcheck: skipped (no content root configured)")
        return
    repo_root = Path(__file__).resolve().parents[2]
    issues = run_content_coverage_healthcheck(
        content_root=service.content_repository.root,
        schema_root=repo_root / "kaggle",
    )
    for issue in issues:
        logger.warning("content-healthcheck: %s", issue)
    if issues and os.getenv("CONTENT_HEALTHCHECK_FAIL_FAST", "0") == "1":
        raise RuntimeError("Content healthcheck failed")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    _run_startup_content_healthcheck()
    yield


app = FastAPI(title="OpAstro Engine API", version=resolve_version("opastro"), lifespan=_lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/horoscope", response_model=HoroscopeResponse)
async def get_horoscope(
    request: HoroscopeRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> HoroscopeResponse:
    timer = Timer()
    tenant = request.tenant_id or x_tenant_id
    birth = request.birth
    cache_key = build_cache_key(
        tenant_id=tenant,
        period=request.period,
        sign=request.sign,
        sign_source="provided" if request.sign else "derived",
        sections=[section.value for section in request.sections] if request.sections else None,
        target_date=request.target_date,
        birth_date=birth.date.isoformat() if birth else None,
        birth_time=birth.time if birth else None,
        birth_latitude=birth.coordinates.latitude if birth and birth.coordinates else None,
        birth_longitude=birth.coordinates.longitude if birth and birth.coordinates else None,
        birth_timezone=birth.timezone if birth else None,
        zodiac_system=request.zodiac_system.value if request.zodiac_system else None,
        ayanamsa=request.ayanamsa.value if request.ayanamsa else None,
        house_system=request.house_system.value if request.house_system else None,
        node_type=request.node_type.value if request.node_type else None,
    )
    cached = cache.get(cache_key)
    if cached:
        metrics.record_cache_hit()
        metrics.record_request(timer.elapsed_ms())
        return HoroscopeResponse.model_validate_json(cached)

    try:
        response = service.generate(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cache.set(cache_key, response.model_dump_json())
    metrics.record_cache_miss()
    metrics.record_request(timer.elapsed_ms())
    return response


@app.post("/birthday-horoscope", response_model=HoroscopeResponse)
async def get_birthday_horoscope(
    request: BirthdayHoroscopeRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> HoroscopeResponse:
    timer = Timer()
    tenant = request.tenant_id or x_tenant_id
    birth = request.birth
    cache_key = build_cache_key(
        tenant_id=tenant,
        period=Period.YEARLY,
        sign=request.sign,
        sign_source="provided" if request.sign else "derived",
        sections=[section.value for section in request.sections] if request.sections else None,
        target_date=request.target_date,
        birth_date=birth.date.isoformat() if birth else None,
        birth_time=birth.time if birth else None,
        birth_latitude=birth.coordinates.latitude if birth and birth.coordinates else None,
        birth_longitude=birth.coordinates.longitude if birth and birth.coordinates else None,
        birth_timezone=birth.timezone if birth else None,
        zodiac_system=request.zodiac_system.value if request.zodiac_system else None,
        ayanamsa=request.ayanamsa.value if request.ayanamsa else None,
        house_system=request.house_system.value if request.house_system else None,
        node_type=request.node_type.value if request.node_type else None,
        key_namespace="birthday_horoscope",
    )
    cached = cache.get(cache_key)
    if cached:
        metrics.record_cache_hit()
        metrics.record_request(timer.elapsed_ms())
        return HoroscopeResponse.model_validate_json(cached)

    try:
        response = service.generate_birthday(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cache.set(cache_key, response.model_dump_json())
    metrics.record_cache_miss()
    metrics.record_request(timer.elapsed_ms())
    return response


@app.post("/planet-horoscope", response_model=HoroscopeResponse)
async def get_planet_horoscope(
    request: PlanetHoroscopeRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> HoroscopeResponse:
    timer = Timer()
    tenant = request.tenant_id or x_tenant_id
    birth = request.birth
    cache_key = build_cache_key(
        tenant_id=tenant,
        period=request.period,
        sign=request.sign,
        sign_source="provided" if request.sign else "derived",
        sections=[section.value for section in request.sections] if request.sections else None,
        target_date=request.target_date,
        birth_date=birth.date.isoformat() if birth else None,
        birth_time=birth.time if birth else None,
        birth_latitude=birth.coordinates.latitude if birth and birth.coordinates else None,
        birth_longitude=birth.coordinates.longitude if birth and birth.coordinates else None,
        birth_timezone=birth.timezone if birth else None,
        zodiac_system=request.zodiac_system.value if request.zodiac_system else None,
        ayanamsa=request.ayanamsa.value if request.ayanamsa else None,
        house_system=request.house_system.value if request.house_system else None,
        node_type=request.node_type.value if request.node_type else None,
        key_namespace=f"planet_horoscope:{request.planet.value}",
    )
    cached = cache.get(cache_key)
    if cached:
        metrics.record_cache_hit()
        metrics.record_request(timer.elapsed_ms())
        return HoroscopeResponse.model_validate_json(cached)

    try:
        response = service.generate_planet(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cache.set(cache_key, response.model_dump_json())
    metrics.record_cache_miss()
    metrics.record_request(timer.elapsed_ms())
    return response


@app.post("/natal-birthchart", response_model=NatalBirthchartResponse)
@app.post("/natal-birthchart-report", response_model=NatalBirthchartResponse)
async def get_natal_birthchart_report(
    request: NatalBirthchartRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> NatalBirthchartResponse:
    timer = Timer()
    tenant = request.tenant_id or x_tenant_id
    try:
        response = _get_natal_report(request, tenant)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    metrics.record_request(timer.elapsed_ms())
    return response


def _get_natal_report(request: NatalBirthchartRequest, tenant: str | None) -> NatalBirthchartResponse:
    birth = request.birth
    cache_key = build_cache_key(
        tenant_id=tenant,
        period=Period.YEARLY,
        sign=None,
        sign_source="derived",
        sections=None,
        target_date=birth.date,
        birth_date=birth.date.isoformat(),
        birth_time=birth.time,
        birth_latitude=birth.coordinates.latitude if birth.coordinates else None,
        birth_longitude=birth.coordinates.longitude if birth.coordinates else None,
        birth_timezone=birth.timezone,
        zodiac_system=request.zodiac_system.value if request.zodiac_system else None,
        ayanamsa=request.ayanamsa.value if request.ayanamsa else None,
        house_system=request.house_system.value if request.house_system else None,
        node_type=request.node_type.value if request.node_type else None,
        user_name=request.user_name,
        key_namespace="natal_birthchart",
    )
    cached = cache.get(cache_key)
    if cached:
        metrics.record_cache_hit()
        return NatalBirthchartResponse.model_validate_json(cached)

    response = service.generate_natal_birthchart(request)
    cache.set(cache_key, response.model_dump_json())
    metrics.record_cache_miss()
    return response


@app.post("/natal-birthchart/wheel.svg")
async def get_natal_wheel_svg(
    request: NatalBirthchartRequest,
    theme: str = Query(default="night", pattern="^(night|day)$"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> Response:
    timer = Timer()
    tenant = request.tenant_id or x_tenant_id
    try:
        report = _get_natal_report(request, tenant)
        svg = build_natal_wheel_svg(report, theme=theme)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    metrics.record_request(timer.elapsed_ms())
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")


@app.post("/natal-birthchart/wheel.png")
async def get_natal_wheel_png(
    request: NatalBirthchartRequest,
    theme: str = Query(default="night", pattern="^(night|day)$"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> Response:
    timer = Timer()
    tenant = request.tenant_id or x_tenant_id
    try:
        report = _get_natal_report(request, tenant)
        png_bytes = build_natal_wheel_png(report, theme=theme)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    metrics.record_request(timer.elapsed_ms())
    return Response(content=png_bytes, media_type="image/png")


@app.post("/natal-birthchart/house-overlay")
async def get_natal_house_overlay(
    request: NatalBirthchartRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> JSONResponse:
    timer = Timer()
    tenant = request.tenant_id or x_tenant_id
    try:
        report = _get_natal_report(request, tenant)
        payload = build_house_overlay_map(report)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    metrics.record_request(timer.elapsed_ms())
    return JSONResponse(content=payload)


@app.post("/natal-birthchart/report.pdf")
async def get_natal_report_pdf(
    request: NatalBirthchartRequest,
    theme: str = Query(default="night", pattern="^(night|day)$"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> Response:
    timer = Timer()
    tenant = request.tenant_id or x_tenant_id
    try:
        report = _get_natal_report(request, tenant)
        pdf_bytes = build_natal_report_pdf(report, wheel_theme=theme)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    metrics.record_request(timer.elapsed_ms())
    headers = {"Content-Disposition": 'attachment; filename="opastro-natal-report.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.get("/metrics")
async def get_metrics() -> dict:
    snap = metrics.snapshot()
    return {
        "requests": snap.requests,
        "cache_hits": snap.cache_hits,
        "cache_misses": snap.cache_misses,
        "avg_latency_ms": snap.avg_latency_ms,
    }


@app.post("/admin/pregenerate")
async def admin_pregenerate(
    payload: PregenRequest,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> dict:
    expected = os.getenv("PREGEN_TOKEN")
    if expected and x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    total = pregenerate(
        service,
        cache,
        payload.period,
        payload.target_date,
        tenant_id=payload.tenant_id,
    )
    return {"status": "ok", "generated": total}
