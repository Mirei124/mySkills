"""Run Rust capture against private Wayfire, D-Bus, PipeWire and Portal services."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import select
import subprocess
import sys
import tempfile
import time

SKILL=Path(__file__).resolve().parents[1]
def wait_for(check,processes,timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        failed=[name for name,p in processes if p.poll() is not None]
        if failed: raise RuntimeError('ISOLATED_SERVICE_EXITED: '+','.join(failed))
        if check(): return
        time.sleep(.05)
    raise RuntimeError('ISOLATED_SERVICE_READY_TIMEOUT')

def inside(root):
    root=Path(root)
    env=os.environ.copy()
    target_output=env.get('WF_ISOLATED_TARGET_OUTPUT','HEADLESS-1')
    processes=[]
    logs=[]
    def launch(name,args):
        log=(root/(name+'.log')).open('w');logs.append(log)
        p=subprocess.Popen(args,env=env,stdout=log,stderr=log)
        processes.append((name,p));return p
    def bus_has(name):
        r=subprocess.run(['gdbus','call','--session','--dest','org.freedesktop.DBus','--object-path','/org/freedesktop/DBus','--method','org.freedesktop.DBus.NameHasOwner',name],env=env,capture_output=True,text=True,timeout=2)
        return 'true' in r.stdout
    try:
        launch('wayfire',['/usr/bin/wayfire','-c',str(root/'wayfire.ini')])
        launch('pipewire',['/usr/bin/pipewire','-c',str(root/'pipewire.conf')])
        wait_for(lambda:any(p.is_socket() for p in root.glob('wayland-*')) and (root/'pipewire-0').is_socket(),processes)
        sockets=[p for p in root.glob('wayland-*') if p.is_socket()]
        if len(sockets)!=1: raise RuntimeError('AMBIGUOUS_ISOLATED_SOCKET')
        env['WAYLAND_DISPLAY']=sockets[0].name
        env['WF_NOTIFY_FAILURE_FILE']=str(root/'notification-failure')
        launch('wireplumber',['/usr/bin/wireplumber','--profile','policy'])
        launch('notifications',[sys.executable,str(SKILL/'tests/isolated_notifications.py')])
        launch('permission-store',['/usr/lib/xdg-permission-store'])
        launch('portal-wlr',['/usr/lib/xdg-desktop-portal-wlr','-l','DEBUG','-c',str(root/'portal-wlr.conf')])
        wait_for(lambda:bus_has('org.freedesktop.impl.portal.desktop.wlr') and bus_has('org.freedesktop.Notifications'),processes)
        launch('portal',['/usr/lib/xdg-desktop-portal'])
        wait_for(lambda:bus_has('org.freedesktop.portal.Desktop'),processes)
        launch('fixture',[sys.executable,str(SKILL/'tests/desktop_fixture.py'),'--state',str(root/'fixture-state.json'),'--animate'])
        if target_output!='HEADLESS-1':
            wait_for(lambda:(root/'fixture-state.json').exists() and bool(list(root.glob('wayfire-*.socket'))),processes)
            def ipc(method,data=None):
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(3);client.connect(str(next(root.glob('wayfire-*.socket'))))
                    payload=json.dumps({'method':method,'data':data or {}}).encode()
                    client.sendall(len(payload).to_bytes(4,'little')+payload)
                    def exact(n):
                        value=b''
                        while len(value)<n:
                            part=client.recv(n-len(value))
                            if not part:raise RuntimeError('ISOLATED_IPC_CLOSED')
                            value+=part
                        return value
                    return json.loads(exact(int.from_bytes(exact(4),'little')))
            target=next(o for o in ipc('window-rules/list-outputs') if o['name']==target_output)
            state=json.loads((root/'fixture-state.json').read_text())
            view=next(v for v in ipc('window-rules/list-views') if v.get('title')==state['title'])
            moved=ipc('window-rules/configure-view',{'id':view['id'],'output_id':target['id'],'geometry':{'x':100,'y':100,'width':700,'height':400},'tiled-edges':0,'fullscreen':False})
            if moved.get('result')!='ok':raise RuntimeError('ISOLATED_FIXTURE_MOVE_FAILED')
        command=[str(SKILL/'target/debug/wayfire-computer-use'),'probe-capture','--output',target_output,'--path',str(root/'frame.png'),'--auto-select']
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=80)
        input_verified=False
        after=None
        if result.returncode==0 and env.get('WF_ISOLATED_INPUT_TEST')=='1':
            worker=subprocess.Popen([str(SKILL/'target/debug/wayfire-computer-use'),'worker','--output',target_output],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'worker.log').open('w'),text=True)
            processes.append(('input-worker',worker))
            def response():
                if not select.select([worker.stdout],[],[],5)[0]:raise RuntimeError('INPUT_WORKER_RESPONSE_TIMEOUT')
                value=json.loads(worker.stdout.readline())
                if value.get('status')=='error':raise RuntimeError('INPUT_WORKER_ERROR: '+value.get('code','unknown'))
                return value
            def send(action):
                worker.stdin.write(json.dumps({'command':'execute','width':1920,'height':1080,'action':action})+'\n');worker.stdin.flush()
                return response()
            if response().get('status')!='ready':raise RuntimeError('INPUT_WORKER_NOT_READY')
            send({'type':'click','x':300,'y':213,'button':'left'})
            time.sleep(.1)
            state=json.loads((root/'fixture-state.json').read_text())
            if not state['active'] or not state['entry_focused']:raise RuntimeError('ISOLATED_FIXTURE_NOT_FOCUSED')
            send({'type':'type','text':'Rust ASCII 42!'})
            send({'type':'keypress','keys':['CTRL','A']})
            expected='你好，Rust ✓'
            send({'type':'type','text':expected})
            time.sleep(.1)
            state=json.loads((root/'fixture-state.json').read_text())
            if state['text']!=expected:raise RuntimeError('ISOLATED_TEXT_MISMATCH: '+repr(state['text']))
            after_command=command[:];after_command[after_command.index('--path')+1]=str(root/'frame-after-input.png')
            after=subprocess.run(after_command,env=env,capture_output=True,text=True,timeout=80)
            if after.returncode:raise RuntimeError('POST_INPUT_CAPTURE_FAILED: '+after.stdout)
            worker.stdin.write('{"command":"stop"}\n');worker.stdin.flush();response()
            worker.wait(timeout=5)
            if worker.returncode:raise RuntimeError('INPUT_WORKER_EXIT_FAILED')
            input_verified=True
        session_verified=False
        session_frame=None
        if result.returncode==0 and env.get('WF_ISOLATED_SESSION_TEST')=='1':
            binary=str(SKILL/'target/debug/wayfire-computer-use')
            def cli(args,input=None,timeout=15):
                response=subprocess.run([binary,*args],env=env,input=input,capture_output=True,text=True,timeout=timeout)
                value=json.loads(response.stdout)
                return value
            if target_output!='HEADLESS-1':
                before_notices=(root/'notifications.log').read_text()
                unselected=cli(['start','--auto-select-output'],timeout=75)
                if unselected.get('code')!='OUTPUT_CONFIRMATION_REQUIRED':raise RuntimeError('RUST_MULTIPLE_OUTPUTS_NOT_CONFIRMED')
                if (root/'notifications.log').read_text()!=before_notices:raise RuntimeError('RUST_UNSELECTED_OUTPUT_SENT_NOTICE')
            failure=root/'notification-failure'
            failure.write_text('start')
            denied=cli(['start','--output',target_output,'--auto-select-output'],timeout=75)
            failure.unlink()
            if denied.get('status')!='error':raise RuntimeError('RUST_START_NOTIFICATION_FAILURE_NOT_ENFORCED')
            first=cli(['start','--output',target_output,'--auto-select-output'],timeout=75)
            if first.get('status')!='ready':raise RuntimeError('RUST_SESSION_START_FAILED: '+repr(first))
            latest=first
            def envelope(action,identifier):
                return {'request_id':identifier,'session_id':first['session_id'],'observation_id':latest['observation_id'],'action':action}
            def act(action,identifier):
                nonlocal latest
                request=envelope(action,identifier)
                response=cli(['act'],json.dumps(request))
                if response.get('status')!='ok':raise RuntimeError('RUST_SESSION_ACTION_FAILED: '+repr(response))
                latest=response
                return request,response
            act({'type':'click','x':300,'y':213,'button':'left'},'session-click')
            act({'type':'keypress','keys':['CTRL','A']},'session-select')
            expected='Rust session 中文 ✓'
            request,typed=act({'type':'type','text':expected},'session-type')
            duplicate=cli(['act'],json.dumps(request))
            if duplicate!=typed:raise RuntimeError('RUST_DEDUP_RESULT_MISMATCH')
            if json.loads((root/'fixture-state.json').read_text())['text']!=expected:raise RuntimeError('RUST_SESSION_TEXT_MISMATCH')
            for index,action in enumerate([
                {'type':'move','x':300,'y':213},
                {'type':'double_click','x':300,'y':213},
                {'type':'drag','path':[{'x':134,'y':213},{'x':220,'y':213},{'x':300,'y':213}]},
                {'type':'scroll','x':300,'y':213,'scroll_x':40,'scroll_y':80},
                {'type':'wait'},
                {'type':'screenshot'},
            ]):act(action,'mouse-'+str(index))
            events=json.loads((root/'fixture-state.json').read_text())['events']
            if not any(e['type']=='2button-press' for e in events):raise RuntimeError('RUST_DOUBLE_CLICK_NOT_OBSERVED')
            if not any(e['type']=='scroll' for e in events):raise RuntimeError('RUST_SCROLL_NOT_OBSERVED')
            import shutil
            session_frame=root/'session-after-input.png'
            shutil.copyfile(latest['screenshot_path'],session_frame)
            stale=cli(['act'],json.dumps({'request_id':'stale-test','session_id':first['session_id'],'observation_id':first['observation_id'],'action':{'type':'click','x':300,'y':213,'button':'left'}}))
            if stale.get('code')!='STALE_OBSERVATION' or stale.get('action_executed') is not False:raise RuntimeError('RUST_STALE_OBSERVATION_FAILURE')
            wait_request=envelope({'type':'wait'},'cancel-wait')
            pending=subprocess.Popen([binary,'act'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            pending.stdin.write(json.dumps(wait_request));pending.stdin.close()
            time.sleep(.05)
            before=time.monotonic()
            stopped=cli(['stop'])
            elapsed=time.monotonic()-before
            cancelled=json.loads(pending.stdout.read());pending.wait(timeout=3)
            if stopped!={'status':'stopped','errors':[]}:raise RuntimeError('RUST_STOP_FAILED: '+repr(stopped))
            if cancelled.get('code')!='ACTION_CANCELLED':raise RuntimeError('RUST_CANCEL_FAILED: '+repr(cancelled))
            if elapsed>2:raise RuntimeError('RUST_STOP_TOO_SLOW')
            if cli(['stop'])!=stopped:raise RuntimeError('RUST_REPEAT_STOP_FAILED')
            if Path(typed['screenshot_path']).exists():raise RuntimeError('RUST_SCREENSHOT_NOT_CLEANED')
            next_ready=cli(['start','--output',target_output,'--auto-select-output'],timeout=75)
            if next_ready.get('status')!='ready':raise RuntimeError('RUST_SECOND_START_FAILED')
            failure.write_text('end')
            failed_notice=cli(['stop'])
            failure.unlink()
            if failed_notice.get('status')!='stopped' or not any('END_NOTIFICATION_FAILED' in e for e in failed_notice.get('errors',[])):
                raise RuntimeError('RUST_END_NOTIFICATION_FAILURE_NOT_REPORTED')
            third=cli(['start','--output',target_output,'--auto-select-output'],timeout=75)
            if third.get('status')!='ready':raise RuntimeError('RUST_THIRD_START_FAILED')
            import hashlib
            runtime=root/('wf-computer-'+hashlib.sha256(env['WAYLAND_DISPLAY'].encode()).hexdigest()[:16])
            workers=[]
            for entry in Path('/proc').iterdir():
                if not entry.name.isdigit():continue
                try:
                    args=(entry/'cmdline').read_bytes().split(b'\0')
                    private_env=(entry/'environ').read_bytes().split(b'\0')
                    if args[:2]==[binary.encode(),b'worker'] and ('XDG_RUNTIME_DIR='+str(root)).encode() in private_env:workers.append(int(entry.name))
                except (FileNotFoundError,PermissionError,ProcessLookupError):pass
            if len(workers)!=1:raise RuntimeError('RUST_TEST_WORKER_IDENTITY_AMBIGUOUS')
            os.kill(workers[0],signal.SIGKILL)
            deadline=time.monotonic()+5
            while not (runtime/'stopped.json').exists() and time.monotonic()<deadline:time.sleep(.03)
            if not (runtime/'stopped.json').exists():raise RuntimeError('RUST_WORKER_CRASH_NOT_CLEANED')
            if json.loads((runtime/'stopped.json').read_text()).get('errors'):raise RuntimeError('RUST_WORKER_CRASH_CLEANUP_ERRORS')
            if 'Task interrupted; desktop control has stopped.' not in (root/'notifications.log').read_text():raise RuntimeError('RUST_INTERRUPTION_NOTICE_MISSING')
            session_verified=True
        report={'session_verified':session_verified,'session_frame':str(session_frame) if session_frame else None,'input_verified':input_verified,'after_input_capture':after.stdout if after else None,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'directory':str(root),'live_desktop_connected':False}
        (root/'result.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
        return result.returncode
    finally:
        for _,p in reversed(processes):
            if p.poll() is None:p.terminate()
        for _,p in reversed(processes):
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside',type=Path)
    parser.add_argument('--multi-output',action='store_true',help='Create two outputs and test explicit selection of the second')
    parser.add_argument('--session-test',action='store_true',help='Exercise the Rust session CLI, deduplication and cancellation')
    parser.add_argument('--input-test',action='store_true',help='Also exercise the Rust input worker against the isolated GTK fixture')
    args=parser.parse_args()
    if args.inside:return inside(args.inside)
    root=Path(tempfile.mkdtemp(prefix='wf-rust-isolated-'))
    (root/'bus.conf').write_text(f'<busconfig><type>session</type><listen>unix:tmpdir={root}</listen><policy context="default"><allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/><allow send_type="error" send_requested_reply="false"/><allow receive_type="error" receive_requested_reply="false"/></policy></busconfig>')
    portals=root/'portals';portals.mkdir()
    (portals/'wlr.portal').write_text(Path('/usr/share/xdg-desktop-portal/portals/wlr.portal').read_text())
    config=root/'config';(config/'xdg-desktop-portal').mkdir(parents=True)
    (config/'xdg-desktop-portal/portals.conf').write_text('[preferred]\ndefault=wlr\n')
    (root/'wayfire.ini').write_text('[core]\nplugins =\nxwayland = false\n[output:HEADLESS-1]\nmode = 1920x1080\nposition = 0,0\nscale = 1\ntransform = normal\n')
    (root/'portal-wlr.conf').write_text('[screencast]\nchooser_type = simple\nchooser_cmd = slurp -f %o -or\nmax_fps = 30\n')
    (root/'pipewire.conf').write_text('''context.properties = { core.daemon = true core.name = pipewire-0 }
context.spa-libs = { support.* = support/libspa-support }
context.modules = [
 { name = libpipewire-module-protocol-native }
 { name = libpipewire-module-metadata }
 { name = libpipewire-module-spa-node-factory }
 { name = libpipewire-module-client-node }
 { name = libpipewire-module-access }
 { name = libpipewire-module-adapter }
 { name = libpipewire-module-link-factory }
]
''')
    env=os.environ.copy()
    for name in ['WAYLAND_DISPLAY','WAYLAND_SOCKET','DISPLAY','DBUS_SESSION_BUS_ADDRESS','WAYFIRE_SOCKET','PIPEWIRE_REMOTE','PIPEWIRE_RUNTIME_DIR','PIPEWIRE_CONFIG_DIR','PIPEWIRE_CONFIG_NAME']:
        env.pop(name,None)
    env.update(XDG_DESKTOP_PORTAL_DIR=str(portals),XDG_RUNTIME_DIR=str(root),XDG_CONFIG_HOME=str(config),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),XDG_CURRENT_DESKTOP='Wayfire',XDG_SESSION_TYPE='wayland',WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='1',WLR_RENDERER='pixman',WLR_LIBINPUT_NO_DEVICES='1')
    if args.input_test:env['WF_ISOLATED_INPUT_TEST']='1'
    if args.session_test:env['WF_ISOLATED_SESSION_TEST']='1'
    if args.multi_output:
        env['WF_ISOLATED_TARGET_OUTPUT']='HEADLESS-2';env['WLR_HEADLESS_OUTPUTS']='2'
        config=root/'wayfire.ini'
        config.write_text(config.read_text().replace('plugins =\n','plugins = ipc ipc-rules\n')+'\n[output:HEADLESS-2]\nmode = 1920x1080\nposition = 1920,0\nscale = 1\ntransform = normal\n')
    command=['dbus-run-session','--config-file',str(root/'bus.conf'),'--',sys.executable,str(Path(__file__).resolve()),'--inside',str(root)]
    process=subprocess.Popen(command,env=env,start_new_session=True)
    try:return process.wait(timeout=100)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        raise RuntimeError('ISOLATED_TEST_TIMEOUT: '+str(root))

if __name__=='__main__':raise SystemExit(main())
