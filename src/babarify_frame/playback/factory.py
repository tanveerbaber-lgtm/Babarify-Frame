"""Engine registry. Engines are imported lazily so a missing library never breaks startup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.playback.contracts import PlaybackEngine


@dataclass(frozen=True)
class EngineProbe:
    name: str
    available: bool
    version: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class EngineDescriptor:
    name: str
    display_name: str
    create: Callable[[], PlaybackEngine]
    probe: Callable[[], EngineProbe]


class EngineFactory:
    def __init__(self) -> None:
        self._engines: dict[str, EngineDescriptor] = {}

    def register(self, descriptor: EngineDescriptor) -> None:
        self._engines[descriptor.name] = descriptor

    def names(self) -> list[str]:
        return list(self._engines)

    def descriptor(self, name: str) -> EngineDescriptor:
        try:
            return self._engines[name]
        except KeyError:
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, f"unknown engine '{name}'") from None

    def probe(self, name: str) -> EngineProbe:
        try:
            return self.descriptor(name).probe()
        except PlaybackError:
            raise
        except Exception as exc:
            return EngineProbe(name, False, detail=f"{type(exc).__name__}: {exc}")

    def create(self, name: str) -> PlaybackEngine:
        """Create and initialise an engine. Raises ENGINE_UNAVAILABLE if it cannot load."""
        descriptor = self.descriptor(name)
        try:
            engine = descriptor.create()
        except PlaybackError:
            raise
        except Exception as exc:
            raise PlaybackError(ErrorCode.ENGINE_UNAVAILABLE, f"{name}: {type(exc).__name__}: {exc}") from exc
        engine.initialize()
        return engine


def _create_mock() -> PlaybackEngine:
    from babarify_frame.playback.adapters.mock import MockEngine

    return MockEngine()


def _probe_mock() -> EngineProbe:
    return EngineProbe("mock", True, "1", "simulated engine for tests")


def _create_libvlc() -> PlaybackEngine:
    from babarify_frame.playback.adapters.libvlc import LibVlcEngine

    return LibVlcEngine()


def _probe_libvlc() -> EngineProbe:
    from babarify_frame.playback.adapters.libvlc import probe

    return probe()


def _create_mpv() -> PlaybackEngine:
    from babarify_frame.playback.adapters.mpv import MpvEngine

    return MpvEngine()


def _probe_mpv() -> EngineProbe:
    from babarify_frame.playback.adapters.mpv import probe

    return probe()


def default_factory() -> EngineFactory:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock (tests)", _create_mock, _probe_mock))
    factory.register(EngineDescriptor("libvlc", "libVLC (candidate)", _create_libvlc, _probe_libvlc))
    factory.register(EngineDescriptor("mpv", "mpv (candidate)", _create_mpv, _probe_mpv))
    return factory
