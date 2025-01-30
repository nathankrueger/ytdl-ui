import tempfile
import pytest

# workaround for running in debugger -- it picks up pytest.ini this way
if __name__ == '__main__':
    pytest.main(['-s'])

import ytdl_ui.util as util

def test_bytes_human_readable():
    assert util.bytes_human_readable(0) == "0 B"
    assert util.bytes_human_readable(0.0) == "0 B"
    assert util.bytes_human_readable(None) == ""

def test_bytes_per_sec_human_readable():
    assert util.bytes_per_sec_human_readable(0) == "0 B/s"
    assert util.bytes_per_sec_human_readable(0.0) == "0 B/s"
    assert util.bytes_per_sec_human_readable(None) == ""

def test_seconds_human_readable():
    assert util.seconds_human_readable(0) == "00:00"
    assert util.seconds_human_readable(0.0) == "00:00"