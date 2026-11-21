"""Test accessibility lookup and native input on disposable toolkit windows."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import quote


def run_toolkits(root, env, binary, output, ipc):
    def cli(*args, body=None):
        result = subprocess.run([binary,*args], env=env, text=True,
                                input=json.dumps(body) if body else None,
                                capture_output=True, timeout=75)
        return json.loads(result.stdout)

    subprocess.run(['gdbus','call','--session','--dest','org.a11y.Bus','--object-path','/org/a11y/bus',
                        '--method','org.freedesktop.DBus.Properties.Set','org.a11y.Status','IsEnabled','<true>'],
                       env=env,capture_output=True,check=True)
    selected = next(o for o in ipc('window-rules/list-outputs') if o['name']==output)
    displays = root/'private-display'
    display = displays.read_text().strip()
    assert display.startswith(':') and display[1:].isdigit(), display
    report = {}
    for name in ('terminal','qt','xwayland','qt-entry','xwayland-entry','xwayland-file','chromium','electron'):
        title = 'Wayfire probe ' + name
        label = 'Confirm probe'
        case_env = {**env,'LANGUAGE':'C','LC_ALL':'C.UTF-8'}
        if name == 'qt':
            command=['kdialog','--title',title,'--yes-label',label,'--yesno','Confirm the isolated test']
            case_env.update(QT_QPA_PLATFORM='wayland',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1')
        elif name == 'xwayland':
            case_env.update(DISPLAY=display,GDK_BACKEND='x11')
            command=['zenity','--question','--title',title,'--text','Confirm the isolated test',
                     '--ok-label',label]
        elif name == 'qt-entry':
            command=['kdialog','--title',title,'--inputbox','Paste the test text']
            case_env.update(QT_QPA_PLATFORM='wayland',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1')
        elif name == 'xwayland-entry':
            case_env.update(DISPLAY=display,GDK_BACKEND='x11')
            command=['zenity','--entry','--title',title,'--text','Paste the test text']
        elif name == 'xwayland-file':
            directory=root/'chooser-fixture'
            directory.mkdir()
            chosen=directory/'probe-document.txt'
            chosen.write_text('Isolated file chooser test')
            label='OK'
            case_env.update(DISPLAY=display,GDK_BACKEND='x11')
            command=['zenity','--file-selection','--title',title,'--filename',str(chosen)]
        elif name == 'terminal':
            received=root/'terminal-input.txt'
            reader="import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.readline()); time.sleep(30)"
            command=['kitty','--config','NONE','--title',title,'-o','linux_display_server=wayland',
                     sys.executable,'-c',reader,str(received)]
        else:
            import ast
            address=subprocess.check_output(['gdbus','call','--session','--dest','org.a11y.Bus','--object-path','/org/a11y/bus','--method','org.a11y.Bus.GetAddress'],env=env,text=True)
            case_env.update(AT_SPI_BUS_ADDRESS=ast.literal_eval(address)[0],ACCESSIBILITY_ENABLED='1')
            html=f"""<meta charset=utf-8><title>{title}</title>
<button onclick="document.title='Confirmed probe';field.focus()">{label}</button>
<input id=field oninput="document.title='Input '+this.value">
<div role="group" aria-label="Selection sample" style="font:20px monospace;width:240px"
 onmouseup="document.title='Selected '+getSelection().toString()">ABCDEFGHIJKLMNOP</div>
<div style="width:3500px;height:3500px"></div>
<script>onscroll=()=>document.title='Scrolled '+scrollX+','+scrollY;</script>"""
            url='data:text/html;charset=utf-8,'+quote(html,safe='')
            switches=['--ozone-platform=wayland','--force-renderer-accessibility=complete',
                      '--disable-background-networking','--no-first-run',
                      '--user-data-dir='+str(root/(name+'-profile'))]
            if name == 'chromium':
                command=['chromium',*switches,'--app='+url]
            else:
                main=root/'probe.cjs'
                main.write_text("const {app,BrowserWindow}=require('electron'); let win; app.whenReady().then(()=>{app.setAccessibilitySupportEnabled(true);win=new BrowserWindow({width:700,height:400});win.loadURL("+json.dumps(url)+");});")
                command=['electron',*switches,str(main)]
        result=report[name]={}
        with (root/(name+'-probe.log')).open('w') as log, (root/(name+'-stdout')).open('wb') as stdout:
            child=subprocess.Popen(command,env=case_env,stdout=stdout,stderr=log)
        try:
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                views=ipc('window-rules/list-views')
                matches=[v for v in views if title in v.get('title','')]
                if len(matches)==1:
                    break
                if child.poll() is not None:
                    raise RuntimeError(f'APPLICATION_EXITED_{child.returncode}')
                time.sleep(.1)
            else:
                raise RuntimeError('WINDOW_NOT_FOUND')
            view=matches[0]
            result['window']={k:view.get(k) for k in ('title','id','pid','app-id','type')}
            reply=ipc('window-rules/configure-view',{'id':view['id'],'output_id':selected['id'],
                      'geometry':{'x':150,'y':160,'width':700,'height':400},'tiled-edges':0,'fullscreen':False})
            assert reply.get('result')=='ok',reply
            ready=cli('start','--output',output,'--auto-select-output')
            assert ready['status']=='ready',ready
            focus=cli('toplevel','focus','--id',str(view['id']))
            assert focus.get('focus_confirmed'),focus
            observed=cli('act','--latest',body={'type':'screenshot'})
            assert observed['status']=='ok',observed
            shutil.copyfile(observed['screenshot_path'],root/(name+'-before.png'))
            sample='Test 😀𠀀 e\u0301 中文'
            def act(action):
                nonlocal observed
                observed=cli('act',body={'action':action,'session_id':observed['session_id'],
                    'observation_id':observed['observation_id'],'request_id':str(time.monotonic_ns())})
                assert observed['status']=='ok',observed
            if name=='terminal' or name.endswith('-entry'):
                act({'type':'type','text':sample,'via_clipboard':True,'shift_paste':name=='terminal'})
                act({'type':'keypress','keys':['ENTER']})
                if name.endswith('-entry'):
                    assert child.wait(timeout=3)==0
                    received=root/(name+'-stdout')
                deadline=time.monotonic()+3
                while not received.exists() and time.monotonic()<deadline:
                    time.sleep(.05)
                assert received.read_bytes()==(sample+'\n').encode(),received
                result['paste_verified']=True
                continue
            if name=='xwayland-file':
                tree=cli('ui','tree','--window-id',str(view['id']))
                buttons=[n['name'] for n in tree['nodes'] if n['role'] in ('button','push button')]
                result['button_names']=buttons
                missing=cli('ui','find','--window-id',str(view['id']),'--role','button','--name','Open')
                assert missing.get('nodes')==[] and label in buttons,(missing,buttons)
            found=cli('ui','find','--window-id',str(view['id']),'--role','button','--name',label)
            result['find']=found
            if found.get('status')=='error':
                inspect="""import gi,json
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
root=Atspi.get_desktop(0)
def describe(node,depth):
    info=[node.get_process_id(),node.get_role_name(),node.get_name()]
    if depth:
        info.append([describe(node.get_child_at_index(i),depth-1) for i in range(min(node.get_child_count(),15))])
    return info
print(json.dumps(describe(root,3)))
"""
                diagnostic=subprocess.run([sys.executable,'-c',inspect],env=case_env,capture_output=True,text=True,timeout=8)
                result['registered']=diagnostic.stdout

            assert len(found.get('nodes',[]))==1,found
            center=found['nodes'][0]['center']
            clicked=cli('act',body={'action':{'type':'click','button':'left',**center},
                        'session_id':observed['session_id'],'observation_id':observed['observation_id'],
                        'request_id':'toolkit-'+name})
            assert clicked['status']=='ok',clicked
            shutil.copyfile(clicked['screenshot_path'],root/(name+'-after.png'))
            if name in ('qt','xwayland','xwayland-file'):
                assert child.wait(timeout=3)==0
                if name=='xwayland-file':
                    returned=(root/(name+'-stdout')).read_text().rstrip('\n')
                    assert returned==str(chosen),returned
                    result['selected_file']=returned
            else:
                confirmed=cli('toplevel','wait','--title-regex','Confirmed probe','--timeout','3')
                assert confirmed.get('toplevel',{}).get('id')==view['id'],confirmed
                observed=clicked
                act({'type':'type','text':sample,'via_clipboard':True})
                pasted=cli('toplevel','wait','--title-regex','^Input '+sample+'$','--timeout','3')
                assert pasted.get('toplevel',{}).get('id')==view['id'],pasted
                result['paste_verified']=True
                tree=cli('ui','tree','--window-id',str(view['id']))
                targets=[node for node in tree['nodes'] if node['name']=='Selection sample' and node['bounds']]
                assert len(targets)==1,targets
                bounds=targets[0]['bounds']
                y=bounds['y']+bounds['height']//2
                points=[{'x':bounds['x']+x,'y':y} for x in (1,25,50,75,100)]
                act({'type':'drag','path':points})
                selection=cli('toplevel','wait','--title-regex','^Selected [A-P]{4,}$','--timeout','3')
                selected_title=selection.get('toplevel',{}).get('title','')
                assert selected_title.startswith('Selected '),selection
                substring=selected_title.removeprefix('Selected ')
                assert substring in 'ABCDEFGHIJKLMNOP',substring
                result['drag_selection']=substring
                offsets=[]
                for distance in (80,160,-80):
                    old=ipc('window-rules/list-views')
                    old_title=next(item['title'] for item in old if item['id']==view['id'])
                    act({'type':'scroll','x':center['x'],'y':center['y']+80,
                         'scroll_x':distance,'scroll_y':distance})
                    deadline=time.monotonic()+3
                    while time.monotonic()<deadline:
                        current=next(item['title'] for item in ipc('window-rules/list-views') if item['id']==view['id'])
                        if current.startswith('Scrolled ') and current!=old_title:
                            break
                        time.sleep(.05)
                    else:
                        raise AssertionError(('SCROLL_UNOBSERVED',old_title))
                    time.sleep(.5)
                    current=next(item['title'] for item in ipc('window-rules/list-views') if item['id']==view['id'])
                    offset=list(map(int,current.removeprefix('Scrolled ').split(',')))
                    previous=offsets[-1]['offset'] if offsets else [0,0]
                    assert all((x-y)*distance>0 for x,y in zip(offset,previous)),(previous,offset)
                    offsets.append({'requested_per_axis':distance,'offset':offset})
                result['scroll_samples']=offsets
            result['clicked']=True
        except (RuntimeError,AssertionError,subprocess.TimeoutExpired) as error:
            result['error']=str(error)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            cli('stop')
            (root/'toolkit-results.json').write_text(json.dumps(report,indent=2))
    failed = [name for name, result in report.items() if not result.get('paste_verified' if name=='terminal' or name.endswith('-entry') else 'clicked')]
    assert not failed, (failed, root/"toolkit-results.json")
    return report
