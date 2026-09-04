import pytest

from pygrbl_streamer import GrblStreamer, State


def test_rx_buffer_keeps_the_backward_compatible_default():
    assert GrblStreamer("port").rx_buffer_size == 128


@pytest.mark.parametrize("value", (True, 1.5, "4096"))
def test_rx_buffer_rejects_non_integer_values(value):
    with pytest.raises(TypeError, match="rx_buffer_size"):
        GrblStreamer("port", rx_buffer_size=value)


@pytest.mark.parametrize("value", (0, 1, -1))
def test_rx_buffer_rejects_values_without_payload_capacity(value):
    with pytest.raises(ValueError, match="rx_buffer_size"):
        GrblStreamer("port", rx_buffer_size=value)


def test_stream_uses_the_configured_receive_buffer():
    laser = GrblStreamer("port", rx_buffer_size=13)
    laser.state = State.IDLE
    sent = []
    waits_after_sent_count = []
    laser.write_line = sent.append

    def acknowledge(_timeout):
        waits_after_sent_count.append(len(sent))
        return "ok"

    laser._wait_ack = acknowledge

    assert laser.stream(("G1X1", "G1X2", "G1X3"), wait_for_idle=False)
    assert sent == ["G1X1", "G1X2", "G1X3"]
    assert waits_after_sent_count[0] == 2
