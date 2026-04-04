"""Branded public API namespace for OpAstro.

This package re-exports the existing `horoscope_engine` implementation so users can import:

    import opastro as oa
    from opastro import ServiceConfig, HoroscopeService, Period, HoroscopeRequest
    from opastro.models import NatalBirthchartRequest
"""

from __future__ import annotations

from importlib import import_module
import sys
from types import ModuleType
from typing import Iterable

from horoscope_engine.config import ServiceConfig
from horoscope_engine.service import HoroscopeService
from horoscope_engine.versioning import resolve_version

_NAMESPACE_MODULES = (
    "aggregation",
    "api",
    "cache",
    "cache_keys",
    "cli",
    "config",
    "content_repository",
    "ephemeris",
    "generation_preflight",
    "healthcheck",
    "main",
    "models",
    "natal_artifacts",
    "observability",
    "pregen",
    "profiles",
    "service",
    "versioning",
    "interpretation",
    "interpretation.renderer",
    "interpretation.rules",
)

_SEARCH_MODULES = (
    "horoscope_engine.models",
    "horoscope_engine.natal_artifacts",
    "horoscope_engine.config",
    "horoscope_engine.service",
)


def _register_namespace_aliases(module_names: Iterable[str]) -> None:
    for name in module_names:
        target = import_module(f"horoscope_engine.{name}")
        sys.modules[f"{__name__}.{name}"] = target


def _resolve_attr(name: str) -> object:
    if name in {"ServiceConfig", "HoroscopeService"}:
        return globals()[name]
    for module_name in _SEARCH_MODULES:
        module = import_module(module_name)
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __getattr__(name: str) -> object:
    return _resolve_attr(name)


def __dir__() -> list[str]:
    names = set(globals().keys())
    for module_name in _SEARCH_MODULES:
        module: ModuleType = import_module(module_name)
        names.update(getattr(module, "__all__", []))
        names.update(name for name in module.__dict__.keys() if not name.startswith("_"))
    return sorted(names)


_register_namespace_aliases(_NAMESPACE_MODULES)

__version__ = resolve_version("opastro")
__all__ = [
    "ServiceConfig",
    "HoroscopeService",
    "__version__",
]
