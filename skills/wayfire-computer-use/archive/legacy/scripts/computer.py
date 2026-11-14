#!/usr/bin/env python3
"""Wayfire computer-use diagnostics, action validation, and session CLI."""
import argparse
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

FIELDS = {'screenshot': set(), 'wait': set(), 'move': {'x','y'}, 'click': {'x','y','button'}, 'double_click': {'x','y'}, 'scroll': {'x','y','scroll_x','scroll_y'}, 'drag': {'path'}, 'keypress': {'keys'}, 'type': {'text'}}

def validate(action):
    if not isinstance(action, dict) or action.get('type') not in FIELDS:
        raise ValueError('UNSUPPORTED_ACTION')
    kind = action['type']
    required = FIELDS[kind]
    optional = {'keys'} if kind in {'move','click','double_click','scroll','drag'} else set()
    if not required <= action.keys() or action.keys() - required - optional - {'type'}:
        raise ValueError('INVALID_FIELDS')
    for name in {'x','y','scroll_x','scroll_y'} & action.keys():
        if type(action[name]) is not int:
            raise ValueError('INVALID_COORDINATE')
    if 'button' in action and action['button'] not in {'left','right','middle','wheel','back','forward'}:
        raise ValueError('UNSUPPORTED_BUTTON')
    if 'keys' in action and not (action['keys'] is None and 'keys' in optional) and (not isinstance(action['keys'], list) or any(not isinstance(k,str) or not k for k in action['keys'])):
        raise ValueError('INVALID_KEYS')
    if kind == 'type' and (not isinstance(action['text'],str) or len(action['text']) > 10000):
        raise ValueError('INVALID_TEXT')
    if kind == 'drag':
        path = action['path']
        if not isinstance(path,list) or not 2 <= len(path) <= 1000:
            raise ValueError('INVALID_PATH')
        for point in path:
            if not isinstance(point,dict) or set(point) != {'x','y'} or any(type(v) is not int for v in point.values()):
                raise ValueError('INVALID_PATH')
    return action

def probe(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=8)
        return {'ok': result.returncode == 0, 'stdout': result.stdout, 'stderr': result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'ok': False, 'error': str(exc)}

def doctor():
    display = os.environ.get('WAYLAND_DISPLAY','')
    runtime = os.environ.get('XDG_RUNTIME_DIR','')
    access = {'ok': False, 'code': 'WAYLAND_UNAVAILABLE'}
    if display and runtime:
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(2)
                client.connect(str(Path(runtime) / display))
            access = {'ok': True, 'code': 'CONNECTED'}
        except OSError as exc:
            access = {'ok': False, 'code': 'WAYLAND_ACCESS_DENIED' if exc.errno in (1,13) else 'WAYLAND_UNAVAILABLE', 'message': str(exc)}
    report = {'status':'diagnostic', 'environment': {k:os.environ.get(k) for k in ('XDG_SESSION_TYPE','XDG_CURRENT_DESKTOP','WAYLAND_DISPLAY')}, 'wayland_access':access, 'dependencies':{k:shutil.which(k) for k in ('wayland-info','notify-send','pw-cli','gst-launch-1.0','wayland-scanner','pkg-config')}, 'protocols_and_outputs':probe(['wayland-info']) if access['ok'] else {'ok':False,'error':'Socket inaccessible'}, 'portal':probe(['gdbus','introspect','--session','--dest','org.freedesktop.portal.Desktop','--object-path','/org/freedesktop/portal/desktop']), 'notifications':probe(['gdbus','introspect','--session','--dest','org.freedesktop.Notifications','--object-path','/org/freedesktop/Notifications']), 'pipewire':probe(['pw-cli','info','0']), 'capabilities':{'input_implemented':True,'capture_implemented':True,'runtime_execution_verified':False,'verification_note':'Read IMPLEMENTATION.md for tested configurations; doctor does not send input or capture frames.'}}
    import re
    from outputs import parse_outputs
    raw=report['protocols_and_outputs'].get('stdout','')
    report['protocol_versions']={name:int(version) for name,version in re.findall(r"interface: '([^']+)',\s+version:\s+(\d+)",raw)}
    try: report['outputs']=parse_outputs(raw)
    except ValueError as exc: report['outputs_error']=str(exc)
    helper=Path(__file__).resolve().parents[1]/'native/build/input-helper'
    report['native_probe']=probe([str(helper),'--probe']) if helper.exists() and access['ok'] else {'ok':False,'error':'Helper not built or Wayland inaccessible'}
    report['capture_plugin']=probe(['gst-inspect-1.0','pipewiresrc'])
    report['portal_routes']={str(path):path.read_text() for path in [Path('/usr/share/xdg-desktop-portal/portals/wlr.portal'),Path('/etc/xdg/xdg-desktop-portal/portals.conf'),Path.home()/'.config/xdg-desktop-portal/portals.conf'] if path.is_file()}
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['doctor','validate','start','act','stop','status','capabilities','release_all','_serve'])
    parser.add_argument('--output',help='Confirmed output name (required with multiple outputs)')
    parser.add_argument('--auto-select-single-output',action='store_true',help='Use one explicitly authorized wlrctl click on a new single-display Portal selector')
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            result = doctor()
        elif args.command == 'validate':
            import sys
            result = {'status':'valid','action':validate(json.load(sys.stdin))}
        else:
            import asyncio
            import sys
            from session import serve, start, send
            if args.command == '_serve':
                asyncio.run(serve(args.output,args.auto_select_single_output))
                return 0
            if args.command == 'start':
                result = asyncio.run(start(args.output,args.auto_select_single_output))
            elif args.command == 'act':
                result = asyncio.run(send(json.load(sys.stdin)))
            else:
                result = asyncio.run(send({'command':args.command}))
        print(json.dumps(result,ensure_ascii=False))
        return 1 if result.get('status') == 'error' else 0
    except (ValueError,TypeError,OSError,RuntimeError) as exc:
        print(json.dumps({'status':'error','code':str(exc),'retryable':False,'action_executed':False}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
