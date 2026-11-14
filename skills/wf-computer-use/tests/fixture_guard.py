"""Fail closed if the dedicated test target is missing or lacks focus."""
import json
import os
from pathlib import Path
import subprocess

def require_fixture(state_path, keyboard=True):
    state=json.loads(Path(state_path).read_text())
    pid=state['pid']
    if type(pid) is not int or pid<=1: raise RuntimeError('FIXTURE_INVALID_PID')
    os.kill(pid,0)
    command=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    if not any(part.endswith(b'/desktop_fixture.py') for part in command):
        raise RuntimeError('FIXTURE_PROCESS_MISMATCH')
    if not state['title'].startswith('Wayfire Computer Use Test ') or not state['title'].endswith(state['token']):
        raise RuntimeError('FIXTURE_IDENTITY_MISMATCH')
    result=subprocess.run(['wlrctl','toplevel','find','title:'+state['title'],'state:active'],capture_output=True,timeout=3)
    if result.returncode or not state['active'] or (keyboard and not state['entry_focused']):
        raise RuntimeError('FIXTURE_NOT_FOCUSED')
    return state
