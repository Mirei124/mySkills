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

def reliability_case(root,env,processes,target,ipc=None):
    case=env['WF_RELIABILITY_CASE']
    binary=str(SKILL/'target/debug/wayfire-computer-use')
    def cli(args,body=None,timeout=80):
        result=subprocess.run([binary,*args],env=env,input=json.dumps(body) if body else None,capture_output=True,text=True,timeout=timeout)
        return json.loads(result.stdout)
    def checkpoint(phase,detail=None):
        record={'phase':phase,'time':time.time(),'services':{name:{'pid':p.pid,'exit_code':p.poll()} for name,p in processes},'detail':detail}
        with (root/'recovery-trace.jsonl').open('a') as out:out.write(json.dumps(record)+'\n')
    def start():
        ready=cli(['start','--output',target,'--auto-select-output'])
        checkpoint('start-result',ready)
        if ready.get('status')!='ready':raise RuntimeError('RELIABILITY_START_FAILED: '+repr(ready))
        return ready
    def request(ready,action):
        return {'request_id':'reliability-'+str(time.monotonic_ns()),'session_id':ready['session_id'],'observation_id':ready['observation_id'],'action':action}
    ready=start();report={'case':case,'live_desktop_connected':False};runtime=Path(ready['screenshot_path']).parent
    if case=='cleanup-gap':
        (root/'notification-failure').write_text('delay-end')
        first=subprocess.Popen([binary,'stop'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+5
        while '"summary": "Computer Use has ended"' not in (root/'notifications.log').read_text() and time.monotonic()<deadline:time.sleep(.01)
        if first.poll() is not None:raise RuntimeError('RELIABILITY_END_DELAY_NOT_REACHED')
        second=cli(['stop'])
        original=json.loads(first.communicate(timeout=5)[0])
        if original!={'status':'stopped','errors':[]} or second!=original:raise RuntimeError('RELIABILITY_LATE_STOP_FAILED: '+repr(second))
        report.update(first=original,late=second)
    elif case=='cycles':
        rss=[];fds=[]
        for index in range(10):
            if index:ready=start()
            pid=ready['owner_pid']
            rss.append(next(line for line in Path(f'/proc/{pid}/status').read_text().splitlines() if line.startswith('VmRSS:')))
            fds.append(len(list(Path(f'/proc/{pid}/fd').iterdir())))
            response=cli(['act'],request(ready,{'type':'screenshot'}))
            if response.get('status')!='ok':raise RuntimeError('RELIABILITY_CAPTURE_FAILED: '+repr(response))
            stopped=cli(['stop'])
            if stopped!={'status':'stopped','errors':[]}:raise RuntimeError('RELIABILITY_STOP_FAILED: '+repr(stopped))
            if Path(ready['screenshot_path']).exists():raise RuntimeError('RELIABILITY_IMAGE_LEAK')
        report.update(cycles=10,rss=rss,fd_counts=fds)
    else:
        if case=='layout':
            subprocess.run(['wlr-randr','--output',target,'--pos','2200,0'],env=env,capture_output=True,text=True,timeout=5,check=True)
            doctor=cli(['doctor'])
            output=next(o for o in doctor['outputs'].values() if o['name']==target)
            if output['position']!=[2200,0]:raise RuntimeError('RELIABILITY_LAYOUT_NOT_APPLIED')
            response=cli(['act'],request(ready,{'type':'click','x':300,'y':213,'button':'left'}))
            if response.get('code')!='LAYOUT_CHANGED' or response.get('action_executed') is not False:raise RuntimeError('RELIABILITY_LAYOUT_INPUT_NOT_BLOCKED: '+repr(response))
        else:
            pending=None
            if case in {'portal-active','session-active','pipewire-active'}:
                response=cli(['act'],request(ready,{'type':'click','x':300,'y':213,'button':'left'}))
                if response.get('status')!='ok':raise RuntimeError('RELIABILITY_FOCUS_FAILED')
                ready=response
                pending=subprocess.Popen([binary,'act'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                pending.stdin.write(json.dumps(request(ready,{'type':'type','text':'aA'*200})));pending.stdin.close()
                deadline=time.monotonic()+5
                while not json.loads((root/'fixture-state.json').read_text())['text'] and time.monotonic()<deadline:time.sleep(.02)
                if not json.loads((root/'fixture-state.json').read_text())['text']:raise RuntimeError('RELIABILITY_TEXT_NOT_STARTED')
            if case in {'session','session-active'}:
                if ipc is None:raise RuntimeError('RELIABILITY_SESSION_REQUIRES_MULTI_OUTPUT')
                # A compositor-driven target loss exercises real session/stream
                # invalidation. Backend Session.Close does not emit Closed.
                subprocess.run(['wlr-randr','--output',target,'--off'],env=env,capture_output=True,text=True,timeout=5,check=True)
                checkpoint('selected-output-disabled')
            elif case=='backend-close':
                destination='org.freedesktop.impl.portal.desktop.wlr'
                tree=subprocess.run(['busctl','--user','--list','tree',destination],env=env,capture_output=True,text=True,timeout=5,check=True).stdout
                paths=[line.strip() for line in tree.splitlines() if line.strip().startswith('/org/freedesktop/portal/desktop/session/') and '/ashpd_' in line]
                if len(paths)!=1:raise RuntimeError('RELIABILITY_SESSION_PATH_AMBIGUOUS: '+repr(paths))
                subprocess.run(['gdbus','call','--session','--dest',destination,'--object-path',paths[0],'--method','org.freedesktop.impl.portal.Session.Close'],env=env,capture_output=True,text=True,timeout=5,check=True)
                checkpoint('after-backend-session-close',{'path':paths[0]})
                if any(p.poll() is not None for name,p in processes if name in {'portal','portal-wlr'}):raise RuntimeError('RELIABILITY_SESSION_CLOSE_KILLED_SERVICE')
            else:
                service=next(p for name,p in processes if name==({'portal-active':'portal','pipewire-active':'pipewire'}.get(case,case)))
                service.terminate();service.wait(timeout=5)
            if case in {'portal','portal-active','portal-wlr','session','session-active','pipewire','pipewire-active'}:
                deadline=time.monotonic()+8
                while not (runtime/'stopped.json').exists() and time.monotonic()<deadline:time.sleep(.02)
                if not (runtime/'stopped.json').exists():raise RuntimeError('RELIABILITY_PORTAL_DID_NOT_AUTOSTOP')
                if pending:
                    cancelled=json.loads(pending.stdout.read());pending.wait(timeout=3)
                    if cancelled.get('code')!='ACTION_CANCELLED' or cancelled.get('action_executed') is not True:raise RuntimeError('RELIABILITY_PORTAL_ACTION_NOT_CANCELLED: '+repr(cancelled))
                    delivered=json.loads((root/'fixture-state.json').read_text())['text'];time.sleep(.3)
                    if not 0<len(delivered)<400 or json.loads((root/'fixture-state.json').read_text())['text']!=delivered:raise RuntimeError('RELIABILITY_PORTAL_INPUT_CONTINUED')
                    report['cancelled']=cancelled
                if (runtime/'socket').exists():raise RuntimeError('RELIABILITY_PORTAL_SOCKET_REMAINED')
            response=cli(['act'],request(ready,{'type':'screenshot'}))
            if response.get('status')!='error':raise RuntimeError('RELIABILITY_LOSS_NOT_REPORTED: '+repr(response))
        before=time.monotonic();stopped=cli(['stop']);elapsed=time.monotonic()-before
        if stopped.get('status')!='stopped':raise RuntimeError('RELIABILITY_LOSS_STOP_FAILED: '+repr(stopped))
        if Path(ready['screenshot_path']).exists():raise RuntimeError('RELIABILITY_LOSS_IMAGE_LEAK')
        report.update(response=response,stop=stopped,stop_seconds=elapsed)
        checkpoint('original-session-stopped',report)
        if case in {'session','session-active','backend-close'}:
            if any(p.poll() is not None for name,p in processes if name=='portal-wlr'):raise RuntimeError('RELIABILITY_BACKEND_EXITED_BEFORE_RECOVERY')
            if case in {'session','session-active'}:
                subprocess.run(['wlr-randr','--output',target,'--on','--pos','1920,0'],env=env,capture_output=True,text=True,timeout=5,check=True)
                output=next(o for o in ipc('window-rules/list-outputs') if o['name']==target)
                state=json.loads((root/'fixture-state.json').read_text())
                view=next(v for v in ipc('window-rules/list-views') if v.get('title')==state['title'])
                moved=ipc('window-rules/configure-view',{'id':view['id'],'output_id':output['id'],'geometry':{'x':100,'y':100,'width':700,'height':400},'tiled-edges':0,'fullscreen':False})
                if moved.get('result')!='ok':raise RuntimeError('RELIABILITY_RESTORED_FIXTURE_MOVE_FAILED')
            replacement=start()
            if replacement['session_id']==ready['session_id']:raise RuntimeError('RELIABILITY_SESSION_NOT_REPLACED')
            observed=cli(['act'],request(replacement,{'type':'screenshot'}))
            if observed.get('status')!='ok':raise RuntimeError('RELIABILITY_REPLACEMENT_CAPTURE_FAILED')
            report['replacement_stop']=cli(['stop'])
            if report['replacement_stop']!={'status':'stopped','errors':[]}:raise RuntimeError('RELIABILITY_REPLACEMENT_CLEANUP_FAILED')
    return report

def toplevel_case(root,env,processes,cli,ipc,ready,latest):
    """Exercise real window identity, focus serialization and stale observations."""
    primary=json.loads((root/'fixture-state.json').read_text())
    secondary_path=root/'secondary-fixture.json'
    with (root/'secondary-fixture.log').open('w') as log:
        secondary=subprocess.Popen([sys.executable,str(SKILL/'tests/desktop_fixture.py'),'--state',str(secondary_path),'--animate'],env=env,stdout=log,stderr=log)
    processes.append(('secondary-fixture',secondary))
    wait_for(secondary_path.exists,processes)
    views=cli(['toplevel','list'])
    if views.get('status')!='ok':raise RuntimeError('TOPLEVEL_LIST_FAILED: '+repr(views))
    first=next(v for v in views['toplevels'] if v['pid']==primary['pid'] and v['title']==primary['title'])
    second=next(v for v in views['toplevels'] if v['pid']==secondary.pid)
    output=next(o for o in ipc('window-rules/list-outputs') if o['name']=='HEADLESS-2')
    moved=ipc('window-rules/configure-view',{'id':second['id'],'output_id':output['id'],'geometry':{'x':850,'y':100,'width':700,'height':400},'tiled-edges':0,'fullscreen':False})
    if moved.get('result')!='ok':raise RuntimeError('TOPLEVEL_FIXTURE_MOVE_FAILED')
    def focus(view):return cli(['toplevel','focus','--id',str(view['id']),'--pid',str(view['pid'])])
    def confirmed(view):
        result=focus(view)
        if result.get('status')!='focused' or result.get('focus_confirmed') is not True or result.get('session_id')!=ready['session_id'] or result.get('observation_id') is not None:
            raise RuntimeError('TOPLEVEL_FOCUS_NOT_CONFIRMED: '+repr(result))
        return result
    def fresh():
        response=cli(['act'],json.dumps({'request_id':'focus-observe-'+str(time.monotonic_ns()),'session_id':ready['session_id'],'observation_id':None,'action':{'type':'screenshot'}}))
        if response.get('status')!='ok':raise RuntimeError('TOPLEVEL_FRESH_CAPTURE_FAILED: '+repr(response))
        return response
    # Exercise the actual owner's connection lifecycle without spawning a CLI
    # process for every poll. Status must not invalidate the observation.
    control=Path(latest['screenshot_path']).parent/'socket'
    def resources():
        process=Path('/proc')/str(ready['owner_pid'])
        rss=next(line.split()[1] for line in (process/'status').read_text().splitlines() if line.startswith('VmRSS:'))
        return {'rss_kib':int(rss),'fds':len(list((process/'fd').iterdir()))}
    time.sleep(.1)
    baseline=resources()
    for _ in range(2_000):
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(3);client.connect(str(control));client.sendall(b'{"command":"status"}\n')
            with client.makefile('r') as response:
                status=json.loads(response.readline())
            if status.get('status')!='active' or status.get('observation_id')!=latest['observation_id']:
                raise RuntimeError('TOPLEVEL_STATUS_LOAD_CHANGED_SESSION')
    time.sleep(.1)
    after_load=resources()
    if after_load['fds']>baseline['fds']+2:raise RuntimeError('TOPLEVEL_STATUS_LOAD_FD_GROWTH')
    (root/'status-load.json').write_text(json.dumps({'requests':2000,'before':baseline,'after':after_load},indent=2))
    confirmed(second)
    stale=cli(['act'],json.dumps({'request_id':'focus-stale','session_id':ready['session_id'],'observation_id':latest['observation_id'],'action':{'type':'click','x':300,'y':213,'button':'left'}}))
    if stale.get('code')!='STALE_OBSERVATION' or stale.get('action_executed') is not False:raise RuntimeError('TOPLEVEL_FOCUS_REUSED_OLD_OBSERVATION')
    confirmed(first)
    latest=fresh()
    # Focus queued after text starts must not redirect its remaining characters.
    before=json.loads((root/'fixture-state.json').read_text())['text']
    suffix=' serialized focus aA'
    pending=subprocess.Popen([str(SKILL/'target/debug/wayfire-computer-use'),'act'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    request={'request_id':'focus-serial-text','session_id':ready['session_id'],'observation_id':latest['observation_id'],'action':{'type':'type','text':suffix}}
    pending.stdin.write(json.dumps(request));pending.stdin.close()
    wait_for(lambda:json.loads((root/'fixture-state.json').read_text())['text']!=before,processes)
    confirmed(second)
    typed=json.loads(pending.stdout.read());pending.wait(timeout=3)
    if typed.get('status')!='ok' or json.loads((root/'fixture-state.json').read_text())['text']!=before+suffix or json.loads(secondary_path.read_text())['text']:
        raise RuntimeError('TOPLEVEL_FOCUS_REDIRECTED_ACTIVE_TEXT')
    confirmed(first)
    other=next(o for o in ipc('window-rules/list-outputs') if o['name']=='HEADLESS-1')
    moved=ipc('window-rules/configure-view',{'id':second['id'],'output_id':other['id'],'geometry':{'x':100,'y':100,'width':700,'height':400},'tiled-edges':0,'fullscreen':False})
    if moved.get('result')!='ok':raise RuntimeError('TOPLEVEL_OTHER_OUTPUT_MOVE_FAILED')
    rejected=focus(second)
    if rejected.get('code')!='TOPLEVEL_OUTPUT_MISMATCH' or rejected.get('focus_request_may_have_executed') is not False:raise RuntimeError('TOPLEVEL_CROSS_OUTPUT_FOCUS_NOT_BLOCKED: '+repr(rejected))
    secondary.terminate();secondary.wait(timeout=4)
    processes.remove(('secondary-fixture',secondary))
    missing=focus(second)
    if missing.get('code')!='TOPLEVEL_NOT_FOUND' or missing.get('focus_request_may_have_executed') is not False:raise RuntimeError('TOPLEVEL_CLOSED_WINDOW_NOT_REJECTED: '+repr(missing))
    confirmed(first)
    return fresh(),first

def inside(root):
    root=Path(root)
    env=os.environ.copy()
    binary=str(SKILL/'target/debug/wayfire-computer-use')
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
        launch('portal-wlr',[env.get('WF_TEST_PORTAL_WLR_BINARY','/usr/lib/xdg-desktop-portal-wlr'),'-l','DEBUG','-c',str(root/'portal-wlr.conf')])
        wait_for(lambda:bus_has('org.freedesktop.impl.portal.desktop.wlr') and bus_has('org.freedesktop.Notifications'),processes)
        launch('portal',['/usr/lib/xdg-desktop-portal'])
        wait_for(lambda:bus_has('org.freedesktop.portal.Desktop'),processes)
        launch('fixture',[sys.executable,str(SKILL/'tests/desktop_fixture.py'),'--state',str(root/'fixture-state.json'),'--animate'])
        if target_output!='HEADLESS-1':
            wait_for(lambda:(root/'fixture-state.json').exists() and bool(list(root.glob('wayfire-*.socket'))),processes)
            env['WAYFIRE_SOCKET']=str(next(root.glob('wayfire-*.socket')))
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
        reliability=None
        if result.returncode==0 and env.get('WF_RELIABILITY_CASE'):
            reliability=reliability_case(root,env,processes,target_output,ipc if target_output!='HEADLESS-1' else None)
        session_verified=False
        toplevel_verified=False
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
            if env.get('WF_LAUNCHER_BOUNDARY_TEST')=='1':
                launcher=subprocess.Popen([binary,'start','--output',target_output,'--auto-select-output'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
                stdout,stderr=launcher.communicate(timeout=75)
                first=json.loads(stdout)
                try:os.killpg(launcher.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                time.sleep(.1)
                survived=cli(['status'])
                if survived.get('status')!='active':raise RuntimeError('RUST_OWNER_DID_NOT_SURVIVE_LAUNCHER_EXIT: '+repr(survived))
            else:
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
            # The first keyboard event must preserve case, without a prior
            # shortcut activating the virtual keyboard for this client.
            first_text='Rust FIRST AbZ !@_ 中文 aA'
            act({'type':'type','text':first_text},'session-first-type')
            if json.loads((root/'fixture-state.json').read_text())['text']!=first_text:raise RuntimeError('RUST_FIRST_TEXT_CASE_MISMATCH')
            rejected=cli(['act'],json.dumps(envelope({'type':'type','text':'must not type 😀 suffix'},'unsupported-non-bmp')))
            if rejected.get('code')!='UNSUPPORTED_NON_BMP_TEXT' or rejected.get('action_executed') is not False:raise RuntimeError('RUST_NON_BMP_NOT_REJECTED_BEFORE_INPUT')
            if json.loads((root/'fixture-state.json').read_text())['text']!=first_text:raise RuntimeError('RUST_NON_BMP_TYPED_PREFIX')
            if cli(['status'])['observation_id']!=latest['observation_id']:raise RuntimeError('RUST_NON_BMP_CHANGED_OBSERVATION')
            act({'type':'keypress','keys':['CTRL','A']},'session-select')
            expected='Rust session 中文 ✓'
            request,typed=act({'type':'type','text':expected},'session-type')
            duplicate=cli(['act'],json.dumps(request))
            if duplicate!=typed:raise RuntimeError('RUST_DEDUP_RESULT_MISMATCH')
            if json.loads((root/'fixture-state.json').read_text())['text']!=expected:raise RuntimeError('RUST_SESSION_TEXT_MISMATCH')
            if env.get('WF_ISOLATED_TOPLEVEL_TEST')=='1':
                latest,toplevel_primary=toplevel_case(root,env,processes,cli,ipc,first,latest)
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
            if env.get('WF_ISOLATED_TOPLEVEL_TEST')=='1':
                wait_for(lambda:not (Path(typed['screenshot_path']).parent/'socket').exists(),processes)
                standalone=cli(['toplevel','focus','--id',str(toplevel_primary['id']),'--pid',str(toplevel_primary['pid'])])
                if standalone.get('status')!='focused' or 'session_id' in standalone:raise RuntimeError('TOPLEVEL_STANDALONE_FOCUS_FAILED: '+repr(standalone))
                mismatch=cli(['toplevel','focus','--id',str(toplevel_primary['id']),'--pid','1'])
                if mismatch.get('code')!='TOPLEVEL_IDENTITY_CHANGED' or mismatch.get('focus_request_may_have_executed') is not False:raise RuntimeError('TOPLEVEL_PID_GUARD_FAILED')
                toplevel_verified=True
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
            # Exercise cancellation inside the new cancellable text-settling
            # waits, after observing actual partial delivery to the fixture.
            first=cli(['start','--output',target_output,'--auto-select-output'],timeout=75)
            if first.get('status')!='ready':raise RuntimeError('RUST_TEXT_CANCEL_START_FAILED')
            latest=first
            act({'type':'click','x':300,'y':213,'button':'left'},'cancel-text-click')
            act({'type':'keypress','keys':['CTRL','A']},'cancel-text-select')
            act({'type':'keypress','keys':['BACKSPACE']},'cancel-text-clear')
            pending=subprocess.Popen([binary,'act'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            pending.stdin.write(json.dumps(envelope({'type':'type','text':'aA'*200},'cancel-text')));pending.stdin.close()
            wait_for(lambda:bool(json.loads((root/'fixture-state.json').read_text())['text']),processes,timeout=5)
            before=time.monotonic()
            stopped=cli(['stop'])
            elapsed=time.monotonic()-before
            cancelled=json.loads(pending.stdout.read());pending.wait(timeout=3)
            if stopped!={'status':'stopped','errors':[]} or elapsed>2:raise RuntimeError('RUST_TEXT_CANCEL_STOP_FAILED')
            if cancelled.get('code')!='ACTION_CANCELLED' or cancelled.get('action_executed') is not True:raise RuntimeError('RUST_TEXT_CANCEL_RESULT_FAILED: '+repr(cancelled))
            delivered=json.loads((root/'fixture-state.json').read_text())['text']
            time.sleep(.3)
            if not 0<len(delivered)<400 or json.loads((root/'fixture-state.json').read_text())['text']!=delivered:raise RuntimeError('RUST_TEXT_CONTINUED_AFTER_STOP')
            if list(runtime.glob('o-*.png')):raise RuntimeError('RUST_TEXT_CANCEL_SCREENSHOT_LEAK')
            session_verified=True
        report={'toplevel_verified':toplevel_verified,'reliability':reliability,'session_verified':session_verified,'session_frame':str(session_frame) if session_frame else None,'input_verified':input_verified,'after_input_capture':after.stdout if after else None,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'directory':str(root),'live_desktop_connected':False}
        (root/'result.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
        return result.returncode
    finally:
        (root/'pre-cleanup-processes.json').write_text(json.dumps({name:{'pid':p.pid,'exit_code':p.poll()} for name,p in processes},indent=2))
        # Keep the private bus/services alive while requesting orderly cleanup,
        # including when a reliability assertion intentionally finds a failure.
        try:
            subprocess.run([binary,'stop'],env=env,capture_output=True,text=True,timeout=12)
        except (OSError,subprocess.TimeoutExpired):pass
        # Detached owners do not belong to the harness process group. Match the
        # executable and private runtime before terminating test-only children.
        for entry in Path('/proc').iterdir():
            if not entry.name.isdecimal():continue
            try:
                argv=(entry/'cmdline').read_bytes().split(b'\0')
                private_env=(entry/'environ').read_bytes().split(b'\0')
                if argv[:2] in ([binary.encode(),b'serve'],[binary.encode(),b'worker']) and ('XDG_RUNTIME_DIR='+str(root)).encode() in private_env:
                    os.kill(int(entry.name),signal.SIGTERM)
            except (FileNotFoundError,PermissionError,ProcessLookupError):pass
        for _,p in reversed(processes):
            if p.poll() is None:p.terminate()
        for _,p in reversed(processes):
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside',type=Path)
    parser.add_argument('--portal-wlr-binary',type=Path,help='Use a specified backend executable only inside the private test environment')
    parser.add_argument('--reliability-case',choices=['backend-close','session','session-active','pipewire-active','cleanup-gap','cycles','layout','pipewire','portal','portal-active','portal-wlr','wayfire'],help='Exercise one isolated lifecycle or service-loss case')
    parser.add_argument('--launcher-boundary-test',action='store_true',help='Destroy the launching command process group after readiness and check owner survival')
    parser.add_argument('--multi-output',action='store_true',help='Create two outputs and test explicit selection of the second')
    parser.add_argument('--session-test',action='store_true',help='Exercise the Rust session CLI, deduplication and cancellation')
    parser.add_argument('--toplevel-test',action='store_true',help='Also exercise IPC window listing, focus and action serialization (requires --multi-output --session-test)')
    parser.add_argument('--input-test',action='store_true',help='Also exercise the Rust input worker against the isolated GTK fixture')
    args=parser.parse_args()
    if args.inside:return inside(args.inside)
    if args.toplevel_test and not (args.multi_output and args.session_test):parser.error('--toplevel-test requires --multi-output --session-test')
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
    if args.portal_wlr_binary:env['WF_TEST_PORTAL_WLR_BINARY']=str(args.portal_wlr_binary.resolve(strict=True))
    if args.reliability_case:env['WF_RELIABILITY_CASE']=args.reliability_case
    if args.input_test:env['WF_ISOLATED_INPUT_TEST']='1'
    if args.session_test:env['WF_ISOLATED_SESSION_TEST']='1'
    if args.toplevel_test:env['WF_ISOLATED_TOPLEVEL_TEST']='1'
    if args.launcher_boundary_test:env['WF_LAUNCHER_BOUNDARY_TEST']='1'
    if args.multi_output:
        env['WF_ISOLATED_TARGET_OUTPUT']='HEADLESS-2';env['WLR_HEADLESS_OUTPUTS']='2'
        config=root/'wayfire.ini'
        config.write_text(config.read_text().replace('plugins =\n','plugins = ipc ipc-rules\n')+'\n[output:HEADLESS-2]\nmode = 1920x1080\nposition = 1920,0\nscale = 1\ntransform = normal\n')
    command=['dbus-run-session','--config-file',str(root/'bus.conf'),'--',sys.executable,str(Path(__file__).resolve()),'--inside',str(root)]
    process=subprocess.Popen(command,env=env,start_new_session=True)
    try:return process.wait(timeout=180 if args.reliability_case else 100)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        raise RuntimeError('ISOLATED_TEST_TIMEOUT: '+str(root))

if __name__=='__main__':raise SystemExit(main())
