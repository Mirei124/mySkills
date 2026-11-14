"""Reproduce missing-keymap selector events in a private headless Wayfire."""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile
import time


def probe(selector, expect_crash):
    root = Path(tempfile.mkdtemp(prefix='wf-slurp-isolated-'))
    root.chmod(0o700)
    config = root / 'wayfire.ini'
    config.write_text('[core]\nplugins =\nxwayland = false\n'
                      '[output:HEADLESS-1]\nmode = 1920x1080\nscale = 1\n')
    env = os.environ.copy()
    for key in ('WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'DISPLAY',
                'DBUS_SESSION_BUS_ADDRESS', 'WAYFIRE_SOCKET', 'WAYLAND_DEBUG'):
        env.pop(key, None)
    env.update(XDG_RUNTIME_DIR=str(root), WLR_BACKENDS='headless',
               WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman',
               WLR_LIBINPUT_NO_DEVICES='1')
    processes = []
    results = {}

    def spawn(command, name, environment=None, **kwargs):
        with (root / (name + '.log')).open('w') as log:
            process = subprocess.Popen(command, env=environment or env,
                                       stderr=log, **kwargs)
        processes.append(process)
        return process

    def run_selector(name):
        selector_env = dict(env, WAYLAND_DEBUG='client')
        process = spawn([str(selector), '-f', 'Monitor: %o', '-or'], name,
                        environment=selector_env, stdout=subprocess.DEVNULL)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=3)
        return {'pid': process.pid, 'exit_code': process.returncode}

    def start_worker(name):
        binary = Path(__file__).resolve().parents[3] / 'skills/wayfire-computer-use/target/release/wayfire-computer-use'
        process = spawn([str(binary), 'worker', '--output', 'HEADLESS-1'], name,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        if not select.select([process.stdout], [], [], 5)[0]:
            raise RuntimeError('WORKER_READY_TIMEOUT')
        ready = json.loads(process.stdout.readline())
        if ready.get('status') != 'ready':
            raise RuntimeError('WORKER_NOT_READY: ' + repr(ready))
        return process

    try:
        compositor = spawn(['/usr/bin/wayfire', '-c', str(config)], 'wayfire',
                           stdout=subprocess.DEVNULL, start_new_session=True)
        sockets = []
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            sockets = [path for path in root.glob('wayland-*') if path.is_socket()]
            if sockets or compositor.poll() is not None:
                break
            time.sleep(.05)
        if len(sockets) != 1 or compositor.poll() is not None:
            raise RuntimeError('PRIVATE_COMPOSITOR_NOT_READY')
        env['WAYLAND_DISPLAY'] = sockets[0].name
        results['baseline'] = run_selector('baseline')
        if results['baseline']['exit_code'] != -signal.SIGTERM:
            raise RuntimeError('SELECTOR_BASELINE_FAILED')

        # Keep one keyboard present while the most recently used keyboard exits.
        # No ordinary key or pointer event is dispatched to another application.
        start_worker('standin')
        worker = start_worker('control-worker')
        worker.stdin.write('{"command":"stop"}\n')
        worker.stdin.flush()
        worker.communicate(timeout=5)
        results['after_worker_stop'] = run_selector('after-worker-stop')
        trace = (root / 'after-worker-stop.log').read_text()
        results['modifiers_without_keymap'] = '.modifiers(' in trace and '.keymap(' not in trace
        expected = -signal.SIGSEGV if expect_crash else -signal.SIGTERM
        if results['after_worker_stop']['exit_code'] != expected:
            raise RuntimeError('SELECTOR_UNEXPECTED_EXIT: ' + repr(results))
        if not results['modifiers_without_keymap']:
            raise RuntimeError('MISSING_KEYMAP_TRIGGER_NOT_REPRODUCED')
        return {'status': 'passed', 'root': str(root), 'results': results,
                'expected_crash': expect_crash, 'live_desktop_modified': False}
    except Exception as error:
        raise RuntimeError(str(error) + '; evidence=' + str(root)) from error
    finally:
        (root / 'result.json').write_text(json.dumps(results, indent=2))
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selector', type=Path, default=Path('/usr/bin/slurp'))
    parser.add_argument('--expect-crash', action='store_true',
                        help='Verify the unpatched SIGSEGV reproduction instead of survival')
    args = parser.parse_args()
    print(json.dumps(probe(args.selector.resolve(strict=True), args.expect_crash)))


if __name__ == '__main__':
    main()
