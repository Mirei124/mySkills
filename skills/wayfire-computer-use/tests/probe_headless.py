"""Opt-in isolated Wayfire output probe; never connects to the live desktop."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from outputs import parse_outputs

CONFIG='''[core]
plugins =
xwayland = false

[output:HEADLESS-1]
mode = 1920x1080
position = -960,0
scale = 2
transform = 180

[output:HEADLESS-2]
mode = 1920x1080
position = 0,0
scale = 1.25
transform = 90
'''

def probe():
    with tempfile.TemporaryDirectory(prefix='wf-isolated-') as directory:
        root=Path(directory)
        config=root/'wayfire.ini'
        config.write_text(CONFIG)
        env=os.environ.copy()
        for name in ['WAYLAND_DISPLAY','DISPLAY','DBUS_SESSION_BUS_ADDRESS','WAYFIRE_SOCKET','WAYLAND_SOCKET']:
            env.pop(name,None)
        env.update(XDG_RUNTIME_DIR=directory,WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='2',WLR_RENDERER='pixman',WLR_LIBINPUT_NO_DEVICES='1')
        with (root/'log').open('w') as log:
            # Bypass user session-launch wrappers with the distribution binary.
            process=subprocess.Popen(['/usr/bin/wayfire','-c',str(config)],env=env,stdout=log,stderr=log,start_new_session=True)
            try:
                sockets=[]
                for _ in range(100):
                    sockets=[p for p in root.glob('wayland-*') if p.is_socket()]
                    if sockets or process.poll() is not None: break
                    time.sleep(.05)
                if not sockets:
                    raise RuntimeError('ISOLATED_START_FAILED: '+(root/'log').read_text()[-2500:])
                if len(sockets)!=1: raise RuntimeError('AMBIGUOUS_ISOLATED_SOCKET')
                env['WAYLAND_DISPLAY']=sockets[0].name
                result=subprocess.run(['wayland-info'],env=env,capture_output=True,text=True,timeout=5,check=True)
                outputs=parse_outputs(result.stdout)
                indexed={o['name']:o for o in outputs}
                expected={'HEADLESS-1':((-960,0),(960,540),'180'),'HEADLESS-2':((0,0),(864,1536),'90')}
                if set(indexed)!=set(expected): raise RuntimeError('ISOLATED_OUTPUT_COUNT_MISMATCH')
                for name,(position,size,rotation) in expected.items():
                    output=indexed[name]
                    if output['position']!=position or output['size']!=size or output.get('transform','').rstrip('°')!=rotation:
                        raise RuntimeError('ISOLATED_GEOMETRY_MISMATCH: '+name)
                return {'status':'passed','backend':'isolated Wayfire headless/pixman','configured_scales':{'HEADLESS-1':2,'HEADLESS-2':1.25},'outputs':outputs,'live_desktop_modified':False,'portal_capture_verified':False,'pointer_mapping_verified':False}
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill();process.wait()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',type=Path,help='Optional JSON report destination')
    args=parser.parse_args()
    result=probe()
    encoded=json.dumps(result,indent=2)+'\n'
    if args.result: args.result.write_text(encoded)
    print(encoded,end='')
