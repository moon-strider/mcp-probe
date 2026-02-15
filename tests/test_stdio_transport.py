from __future__ import annotations

import asyncio
import sys
import tempfile

import pytest

from mcp_probe.transport.stdio import StdioTransport


@pytest.fixture
def echo_script():
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    f.write(
        "import sys, json\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if not line: continue\n"
        "    msg = json.loads(line)\n"
        '    sys.stdout.write(json.dumps(msg) + "\\n")\n'
        "    sys.stdout.flush()\n"
    )
    f.close()
    return f.name


@pytest.fixture
def noisy_script():
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    f.write(
        "import sys, json\n"
        'sys.stdout.write("debug: starting up\\n")\n'
        "sys.stdout.flush()\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if not line: continue\n"
        "    msg = json.loads(line)\n"
        '    sys.stdout.write(json.dumps(msg) + "\\n")\n'
        "    sys.stdout.flush()\n"
    )
    f.close()
    return f.name


@pytest.fixture
def hang_script():
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    f.write("import signal, time\n" "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" "while True: time.sleep(1)\n")
    f.close()
    return f.name


async def test_send_receive(echo_script):
    t = StdioTransport(f"{sys.executable} {echo_script}")
    await t.start()
    try:
        msg = {"jsonrpc": "2.0", "id": 1, "method": "test"}
        await t.send(msg)
        resp = await t.receive(5.0)
        assert resp == msg
    finally:
        await t.stop()


async def test_receive_timeout(echo_script):
    t = StdioTransport(f"{sys.executable} {echo_script}")
    await t.start()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await t.receive(0.1)
    finally:
        await t.stop()


async def test_non_json_lines(noisy_script):
    t = StdioTransport(f"{sys.executable} {noisy_script}")
    await t.start()
    try:
        msg = {"jsonrpc": "2.0", "id": 1, "method": "test"}
        await t.send(msg)
        resp = await t.receive(5.0)
        assert resp == msg
        assert t.non_json_lines >= 1
    finally:
        await t.stop()


async def test_stop_sigterm(echo_script):
    t = StdioTransport(f"{sys.executable} {echo_script}")
    await t.start()
    await t.stop()
    assert t.return_code is not None


async def test_stop_sigkill_on_hang(hang_script):
    t = StdioTransport(f"{sys.executable} {hang_script}")
    await t.start()
    await t.stop()
    assert t.return_code is not None
