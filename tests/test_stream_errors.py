import pytest

from pygrbl_streamer import GrblStreamer, State


@pytest.fixture
def scripted_streamer(monkeypatch):
    """Deliver protocol responses without opening a serial port or polling hardware."""
    def make(rx_buffer_size, responses):
        laser = GrblStreamer("port", rx_buffer_size=rx_buffer_size)
        laser.state = State.IDLE
        responses = iter(responses)
        sent, events, idle_waits = [], [], []

        def write_line(command):
            sent.append(command)
            laser._process_line(next(responses))

        def wait_idle(timeout):
            idle_waits.append(timeout)
            return True

        monkeypatch.setattr(laser, "write_line", write_line)
        monkeypatch.setattr(laser, "_wait_idle", wait_idle)
        monkeypatch.setattr(laser, "_emit", lambda kind, data: events.append((kind, data)))
        return laser, sent, events, idle_waits

    return make


@pytest.mark.parametrize("rx_buffer_size,count,error_index", [
    pytest.param(6, 3, 0, id="waiting-for-buffer-room"),
    pytest.param(128, 3, 0, id="first-final-ack"),
    pytest.param(128, 3, 1, id="middle-final-ack"),
    pytest.param(128, 3, 2, id="last-final-ack"),
    pytest.param(128, 1, 0, id="single-command"),
])
@pytest.mark.parametrize("error", ["error:20", "error 20"])
@pytest.mark.parametrize("stop_on_error", [False, True])
@pytest.mark.parametrize("wait_for_idle", [False, True])
def test_error_policy_applies_to_every_acknowledgement(
    scripted_streamer, rx_buffer_size, count, error_index, error,
    stop_on_error, wait_for_idle,
):
    commands = [f"G1X{i}" for i in range(count)]
    responses = ["ok"] * count
    responses[error_index] = error
    laser, sent, events, idle_waits = scripted_streamer(rx_buffer_size, responses)

    result = laser.stream(commands, total=count, stop_on_error=stop_on_error,
                          wait_for_idle=wait_for_idle)

    assert result is (not stop_on_error)
    assert events.count(("error", error)) == 1
    assert (("progress", (100, "completed")) in events) is (not stop_on_error)
    assert bool(idle_waits) is (wait_for_idle and not stop_on_error)
    expected_sent = commands[:1] if rx_buffer_size == 6 and stop_on_error else commands
    assert sent == expected_sent
    assert laser.state is State.IDLE


@pytest.mark.parametrize("rx_buffer_size", [6, 128])
@pytest.mark.parametrize("stop_on_error", [False, True])
@pytest.mark.parametrize("wait_for_idle", [False, True])
def test_successful_stream_keeps_its_completion_behavior(
    scripted_streamer, rx_buffer_size, stop_on_error, wait_for_idle,
):
    commands = ["G1X1", "G1X2", "G1X3"]
    laser, sent, events, idle_waits = scripted_streamer(rx_buffer_size, ["ok"] * 3)

    assert laser.stream(commands, total=3, stop_on_error=stop_on_error,
                        wait_for_idle=wait_for_idle)
    assert sent == commands
    assert events.count(("progress", (100, "completed"))) == 1
    assert not any(kind == "error" for kind, _ in events)
    assert bool(idle_waits) is wait_for_idle
    assert laser.state is State.IDLE
