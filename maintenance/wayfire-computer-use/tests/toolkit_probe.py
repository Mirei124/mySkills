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
    for name in ('qt','xwayland','chromium','electron'):
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
        else:
            import ast
            address=subprocess.check_output(['gdbus','call','--session','--dest','org.a11y.Bus','--object-path','/org/a11y/bus','--method','org.a11y.Bus.GetAddress'],env=env,text=True)
            case_env.update(AT_SPI_BUS_ADDRESS=ast.literal_eval(address)[0],ACCESSIBILITY_ENABLED='1')
            html=f'<title>{title}</title><button onclick="document.title=\'Confirmed probe\'">{label}</button>'
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
        with (root/(name+'-probe.log')).open('w') as log:
            child=subprocess.Popen(command,env=case_env,stdout=log,stderr=log)
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
            if name in ('qt','xwayland'):
                assert child.wait(timeout=3)==0
            else:
                confirmed=cli('toplevel','wait','--title-regex','Confirmed probe','--timeout','3')
                assert confirmed.get('toplevel',{}).get('id')==view['id'],confirmed
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
    failed = [name for name, result in report.items() if not result.get("clicked")]
    assert not failed, (failed, root/"toolkit-results.json")
    return report
