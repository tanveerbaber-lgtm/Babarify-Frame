import pytest

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import PlaybackEvent, StateChanged
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.controller import PlaybackController
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe, default_factory


def mock_factory() -> EngineFactory:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    return factory


def test_default_factory_registers_candidates() -> None:
    assert default_factory().names() == ["mock", "libvlc", "mpv"]


def test_unknown_engine() -> None:
    with pytest.raises(PlaybackError) as exc:
        default_factory().create("gstreamer")
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_create_returns_initialised_engine() -> None:
    engine = default_factory().create("mock")
    assert engine.get_playback_state().state is S.READY
    engine.close()


def test_failing_engine_constructor_maps_to_engine_unavailable() -> None:
    def broken() -> PlaybackEngine:
        raise OSError("libfoo.dll not found")

    factory = EngineFactory()
    factory.register(EngineDescriptor("broken", "Broken", broken, lambda: EngineProbe("broken", False)))
    with pytest.raises(PlaybackError) as exc:
        factory.create("broken")
    assert exc.value.code is ErrorCode.ENGINE_UNAVAILABLE


def test_probe_never_raises_for_engine_failures() -> None:
    def bad_probe() -> EngineProbe:
        raise OSError("boom")

    factory = EngineFactory()
    factory.register(EngineDescriptor("x", "X", MockEngine, bad_probe))
    probe = factory.probe("x")
    assert not probe.available
    assert "boom" in probe.detail


def test_controller_requires_engine() -> None:
    controller = PlaybackController(mock_factory())
    with pytest.raises(PlaybackError) as exc:
        controller.play()
    assert exc.value.code is ErrorCode.INVALID_STATE


def test_controller_forwards_commands_and_events() -> None:
    controller = PlaybackController(mock_factory())
    received: list[PlaybackEvent] = []
    controller.add_listener(received.append)
    controller.start("mock")
    controller.open("mock://clip")
    controller.toggle_play_pause()
    assert controller.status().state is S.PAUSED
    controller.toggle_play_pause()
    assert controller.status().state is S.PLAYING
    assert any(isinstance(e, StateChanged) and e.new is S.PLAYING for e in received)
    controller.shutdown()


def test_controller_reapplies_video_output_on_engine_switch() -> None:
    controller = PlaybackController(mock_factory())
    controller.set_video_output(42)
    controller.start("mock")
    first = controller.engine
    assert isinstance(first, MockEngine) and first.window_id == 42
    controller.start("mock")
    second = controller.engine
    assert first.state is S.CLOSED
    assert isinstance(second, MockEngine) and second.window_id == 42
    controller.shutdown()


def test_controller_shutdown_is_idempotent_and_detaches_listeners() -> None:
    controller = PlaybackController(mock_factory())
    received: list[PlaybackEvent] = []
    controller.add_listener(received.append)
    controller.start("mock")
    engine = controller.engine
    controller.shutdown()
    controller.shutdown()
    assert engine.get_playback_state().state is S.CLOSED
    assert controller.engine_name is None
