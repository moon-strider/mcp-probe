from __future__ import annotations

import asyncio
import os
import sys
import tempfile

import pytest

from mcp_probe.protocol import ProtocolError
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
    f.write("import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nwhile True: time.sleep(1)\n")
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
        with pytest.raises(ProtocolError):
            await t.receive(5.0)
        assert t.non_json_lines == 1
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


async def test_stderr_capture_is_bounded(tmp_path):
    script = tmp_path / "stderr_server.py"
    script.write_text(
        "import sys\n"
        "sys.stderr.write('x' * (1024 * 400))\n"
        "sys.stderr.flush()\n"
        'print(\'{"jsonrpc":"2.0","id":1,"result":{}}\', flush=True)\n'
        "sys.stdin.read()\n"
    )
    t = StdioTransport([sys.executable, str(script)])
    async with t:
        await t.receive(5)
        assert len(t.stderr_output) <= 64 * 4096


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
async def test_stop_terminates_descendants(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    child = tmp_path / "child.py"
    child.write_text(
        "import pathlib, sys, time\n"
        "path = pathlib.Path(sys.argv[1])\n"
        "for count in range(3000):\n"
        "    path.write_text(str(count))\n"
        "    time.sleep(0.01)\n"
    )
    script = tmp_path / "parent.py"
    script.write_text(
        "import subprocess, sys, json, pathlib, time\n"
        "child = subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n"
        "while not pathlib.Path(sys.argv[2]).exists(): time.sleep(0.01)\n"
        "print(json.dumps({'jsonrpc':'2.0','id':1,'result':{}}), flush=True)\n"
        "sys.stdin.read()\n"
    )
    t = StdioTransport([sys.executable, str(script), str(child), str(heartbeat)])
    async with t:
        await t.receive(5)
        before = heartbeat.read_text()
        await asyncio.sleep(0.1)
        assert heartbeat.read_text() != before, "Descendant was not running before cleanup"
    after = heartbeat.read_text()
    await asyncio.sleep(0.1)
    assert heartbeat.read_text() == after, "Descendant kept running after transport cleanup"
