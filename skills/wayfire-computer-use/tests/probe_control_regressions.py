"""Opt-in private Wayfire regressions for queued cancellation and focus locking."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time

SKILL = Path(__file__).resolve().parents[1]


def probe(binary):
    root = Path(tempfile.mkdtemp(prefix='wf-control-regressions-'))
    processes = []

    def launch(command, env, name, **kwargs):
        with (root / (name + '.log')).open('w') as log:
            process = subprocess.Popen(command, env=env, stderr=log, **kwargs)
        processes.append(process)
        return process

    def wait(check):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(.03)
        raise RuntimeError('PRIVATE_READY_TIMEOUT: ' + str(root))

    def desktop(name):
        directory = root / name
        directory.mkdir(mode=0o700)
        config = directory / 'wayfire.ini'
        config.write_text('[core]\nplugins = ipc ipc-rules\nxwayland = false\n'
                          '[output:HEADLESS-1]\nmode = 1920x1080\nscale = 1\n')
        env = os.environ.copy()
        for key in ('WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'DISPLAY',
                    'DBUS_SESSION_BUS_ADDRESS', 'WAYFIRE_SOCKET'):
            env.pop(key, None)
        env.update(XDG_RUNTIME_DIR=str(directory), WLR_BACKENDS='headless',
                   WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman',
                   WLR_LIBINPUT_NO_DEVICES='1')
        compositor = launch(['/usr/bin/wayfire', '-c', str(config)], env, name,
                            stdout=subprocess.DEVNULL, start_new_session=True)
        wait(lambda: any(p.is_socket() for p in directory.glob('wayland-*'))
             and bool(list(directory.glob('wayfire-*.socket'))))
        env['WAYLAND_DISPLAY'] = next(p.name for p in directory.glob('wayland-*') if p.is_socket())
        env['WAYFIRE_SOCKET'] = str(next(directory.glob('wayfire-*.socket')))
        return directory, env, compositor

    def cli(env, args):
        result = subprocess.run([str(binary), *args], env=env, text=True,
                                capture_output=True, timeout=10)
        value = json.loads(result.stdout)
        with (root / 'commands.jsonl').open('a') as log:
            log.write(json.dumps({'args': args, 'result': value}) + '\n')
        return value

    def configure(env, view, x):
        with socket.socket(socket.AF_UNIX) as stream:
            stream.settimeout(3)
            stream.connect(env['WAYFIRE_SOCKET'])
            payload = json.dumps({'method': 'window-rules/configure-view', 'data': {
                'id': view['id'], 'output_id': view['output_id'],
                'geometry': {'x': x, 'y': 100, 'width': 700, 'height': 400},
                'tiled-edges': 0, 'fullscreen': False}}).encode()
            stream.sendall(len(payload).to_bytes(4, 'little') + payload)
            def exact(size):
                data = b''
                while len(data) < size:
                    part = stream.recv(size - len(data))
                    if not part:
                        raise RuntimeError('PRIVATE_IPC_CLOSED')
                    data += part
                return data
            result = json.loads(exact(int.from_bytes(exact(4), 'little')))
            if result.get('result') != 'ok':
                raise RuntimeError('FIXTURE_MOVE_FAILED: ' + repr(result))

    def fixture(env, name, x):
        state = root / (name + '.json')
        process = launch([sys.executable, str(SKILL / 'tests/desktop_fixture.py'),
                          '--state', str(state), '--animate'], env, name,
                         stdout=subprocess.DEVNULL)
        wait(state.exists)
        found = []
        def mapped():
            found[:] = [v for v in cli(env, ['toplevel', 'list'])['toplevels'] if v['pid'] == process.pid]
            return len(found) == 1
        wait(mapped)
        configure(env, found[0], x)
        return state, found[0]

    def focus(env, view):
        return cli(env, ['toplevel', 'focus', '--id', str(view['id']), '--pid', str(view['pid'])])

    try:
        directory, env, compositor = desktop('first-desktop')
        state, target = fixture(env, 'primary-fixture', 100)
        if focus(env, target).get('status') != 'focused':
            raise RuntimeError('INITIAL_FOCUS_FAILED')
        cancellation = []
        for iteration in range(3):
            worker = launch([str(binary), 'worker', '--output', 'HEADLESS-1'], env,
                            'worker-' + str(iteration), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
            if not select.select([worker.stdout], [], [], 5)[0] or json.loads(worker.stdout.readline()).get('status') != 'ready':
                raise RuntimeError('WORKER_NOT_READY')
            click = {'command': 'execute', 'width': 1920, 'height': 1080,
                     'action': {'type': 'click', 'x': 300, 'y': 213, 'button': 'left'}}
            worker.stdin.write(json.dumps(click) + '\n')
            worker.stdin.flush()
            if json.loads(worker.stdout.readline()).get('status') != 'ok':
                raise RuntimeError('FIXTURE_CLICK_FAILED')
            wait(lambda: json.loads(state.read_text())['entry_focused'])
            before = json.loads(state.read_text())['text']
            os.kill(worker.pid, signal.SIGSTOP)
            os.waitpid(worker.pid, os.WUNTRACED)
            for text in ('MUST_NOT_TYPE', 'STILL_REVOKED'):
                worker.stdin.write(json.dumps({'command': 'execute', 'width': 1920,
                    'height': 1080, 'action': {'type': 'type', 'text': text}}) + '\n')
            worker.stdin.write('{"command":"stop"}\n')
            worker.stdin.flush()
            os.kill(worker.pid, signal.SIGUSR1)
            os.kill(worker.pid, signal.SIGCONT)
            output, _ = worker.communicate(timeout=8)
            replies = [json.loads(line) for line in output.splitlines()]
            expected = [{'status': 'error', 'code': 'ACTION_CANCELLED'}] * 2 + [{'status': 'stopped'}]
            if replies != expected or worker.returncode:
                raise RuntimeError('QUEUED_CANCELLATION_FAILED: ' + repr(replies))
            time.sleep(.1)
            if json.loads(state.read_text())['text'] != before:
                raise RuntimeError('INPUT_DELIVERED_AFTER_CANCEL')
            cancellation.append({'iteration': iteration, 'replies': replies, 'text_unchanged': True})

        _, other_env, _ = desktop('second-desktop')
        _, other = fixture(env, 'secondary-fixture', 850)
        if focus(env, other).get('status') != 'focused':
            raise RuntimeError('SECONDARY_FOCUS_FAILED')
        # Keep a real compositor lock held while trying display and runtime aliases.
        lock_root = directory / ('wf-computer-compositor-' + str(compositor.pid))
        with (lock_root / 'lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            busy = focus(env, target)
            alternate = root / 'alternate-client-runtime'
            alternate.mkdir(mode=0o700)
            alias = dict(env, WAYLAND_DISPLAY=str(directory / env['WAYLAND_DISPLAY']),
                         XDG_RUNTIME_DIR=str(alternate))
            alias_result = focus(alias, target)
            mismatched = dict(env, WAYLAND_DISPLAY=str(Path(other_env['XDG_RUNTIME_DIR']) / other_env['WAYLAND_DISPLAY']))
            mismatch_result = focus(mismatched, target)
            invalid_result = focus(dict(env, WAYLAND_DISPLAY='nonexistent-display'), target)
            if busy.get('code') != 'SESSION_BUSY' or alias_result.get('code') != 'SESSION_BUSY':
                raise RuntimeError('COMPOSITOR_LOCK_BYPASSED: ' + repr([busy, alias_result]))
            if mismatch_result.get('code') != 'COMPOSITOR_IDENTITY_MISMATCH' or not invalid_result.get('code', '').startswith('WAYLAND_UNAVAILABLE'):
                raise RuntimeError('MISMATCHED_COMPOSITOR_NOT_REJECTED: ' + repr([mismatch_result, invalid_result]))
            current = next(v['id'] for v in cli(env, ['toplevel', 'list'])['toplevels'] if v['activated'])
            if current != other['id']:
                raise RuntimeError('REJECTED_FOCUS_CHANGED_TARGET')
        if focus(env, target).get('status') != 'focused':
            raise RuntimeError('FOCUS_LOCK_NOT_RELEASED')
        report = {'status': 'passed', 'directory': str(root), 'cancellation': cancellation,
                  'compositor_mismatch_rejected': True, 'display_runtime_aliases_blocked': True,
                  'rejected_focus_preserved_target': True, 'live_desktop_modified': False}
        (root / 'result.json').write_text(json.dumps(report, indent=2))
        return report
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGCONT)
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=SKILL / 'target/debug/wayfire-computer-use')
    args = parser.parse_args()
    print(json.dumps(probe(args.binary.resolve(strict=True))))
