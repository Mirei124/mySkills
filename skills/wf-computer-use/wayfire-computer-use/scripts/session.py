"""Private Unix-socket session owner and CLI transport."""
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from capture import Capture
from input_backend import Input
from outputs import parse_outputs
from portal import Portal


def runtime():
    root=Path(os.environ['XDG_RUNTIME_DIR'])/('wf-computer-'+hashlib.sha256(os.environ['WAYLAND_DISPLAY'].encode()).hexdigest()[:16])
    root.mkdir(mode=0o700,exist_ok=True)
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise RuntimeError('UNSAFE_RUNTIME_DIRECTORY')
    return root

async def notify(summary,body):
    process=await asyncio.create_subprocess_exec('notify-send',summary,body,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
    try:
        code=await asyncio.wait_for(process.wait(),5)
    except asyncio.TimeoutError:
        process.kill();await process.wait();raise RuntimeError('NOTIFICATION_FAILED')
    if code: raise RuntimeError('NOTIFICATION_FAILED')

class Session:
    def __init__(self,root):
        self.root=root
        self.id='s-'+secrets.token_hex(12)
        self.observation=None
        self.cache={}
        self.serial=asyncio.Lock()
        self.done=asyncio.Event()
        self.last=time.monotonic()
        self.started=False
        self.input=None
        self.portal=None
        self.capture=None
        self.paths=[]
        self.active=None
        self.stopping=False
        self.finished=asyncio.Event()
        self.stop_result=None
        self.stop_reason='normal'
        self.bootstrap_attempted=False

    def cancel(self,reason='normal'):
        if self.stopping:
            return
        self.stopping=True
        self.stop_reason=reason
        self.done.set()
        if self.active is not None:
            self.active.cancel()

    async def observe(self):
        token='o-'+secrets.token_hex(12)
        path=self.root/(token+'.png')
        result=await self.capture.observe(path)
        self.paths.append(path)
        if hasattr(self,'width') and (result['width'],result['height'])!=(self.width,self.height):
            self.observation=None
            raise RuntimeError('LAYOUT_CHANGED')
        self.observation=token
        return dict(result,observation_id=token,output=self.portal.output['name'],layout_version=self.layout,timestamp=time.time())

    async def prepare(self,output,auto_select=False):
        self.portal=await Portal().connect()
        async def bootstrap_notice():
            await notify('Computer Use is preparing desktop control','Selecting the sole display with one authorized click. Please avoid desktop input.')
            self.started=True
            self.bootstrap_attempted=True
        streams=await self.portal.start_stream(output,auto_select=auto_select,before_click=bootstrap_notice)
        self.geometry=await self.outputs()
        # The prototype native device currently maps to compositor-global space.
        if len(self.geometry)!=1: raise RuntimeError('MULTI_OUTPUT_INPUT_UNVERIFIED')
        self.layout=hashlib.sha256(json.dumps(self.geometry,sort_keys=True).encode()).hexdigest()
        self.capture=Capture(self.portal,streams['streams'][0][0])
        first=await self.observe()
        self.width,self.height=first['width'],first['height']
        self.input=await Input().start(self.portal.output['name'])
        if not self.started:
            await notify('Computer Use is controlling the desktop','Mouse and keyboard control is active. Please avoid interacting until the end notification.')
        self.started=True
        return dict(first,session_id=self.id,status='ready',selector_click_may_have_executed=self.bootstrap_attempted)

    async def outputs(self):
        process=await asyncio.create_subprocess_exec('wayland-info',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try: data,_=await asyncio.wait_for(process.communicate(),5)
        except asyncio.TimeoutError:
            process.kill();await process.wait();raise RuntimeError('OUTPUT_DISCOVERY_FAILED')
        if process.returncode: raise RuntimeError('OUTPUT_DISCOVERY_FAILED')
        return parse_outputs(data.decode())

    async def request(self,request):
        from computer import validate
        if request.get('command') in {'status','capabilities'}:
            return {'status':'stopping' if self.stopping else 'active','session_id':self.id,'observation_id':self.observation,'capabilities':{'actions':['screenshot','wait','move','click','double_click','drag','scroll','keypress','type'],'multi_output_verified':False,'clipboard':False,'unicode':'GTK-tested with experimental settling delays'}}
        if request.get('command')=='stop':
            self.cancel()
            await self.finished.wait()
            return self.stop_result
        async with self.serial:
            if self.stopping:
                return {'status':'error','code':'SESSION_STOPPING','action_executed':False}
            self.last=time.monotonic()
            command=request.get('command','act')
            if command=='status': return {'status':'active','session_id':self.id,'observation_id':self.observation}
            if command=='release_all':
                await self.input.command('release')
                return {'status':'released'}
            if command!='act': raise ValueError('UNSUPPORTED_COMMAND')
            if set(request)-{'command','request_id','session_id','observation_id','action'}: raise ValueError('INVALID_FIELDS')
            rid=request.get('request_id')
            if not isinstance(rid,str) or not 1<=len(rid)<=128: raise ValueError('INVALID_REQUEST_ID')
            encoded=json.dumps(request,sort_keys=True)
            if rid in self.cache:
                fingerprint,result=self.cache[rid]
                if fingerprint!=encoded: raise ValueError('REQUEST_ID_CONFLICT')
                return result
            if len(self.cache)>=1000: raise ValueError('SESSION_REQUEST_LIMIT')
            if request.get('session_id')!=self.id: raise ValueError('UNKNOWN_SESSION')
            action=validate(request.get('action'))
            executed=False
            self.active=asyncio.current_task()
            try:
                if request.get('observation_id')!=self.observation: raise ValueError('STALE_OBSERVATION')
                if await self.outputs()!=self.geometry:
                    self.observation=None
                    raise ValueError('LAYOUT_CHANGED')
                if action['type']!='screenshot':
                    # Once dispatch starts, failures may represent partial execution.
                    executed=True
                    await asyncio.wait_for(self.input.execute(action,self.width,self.height),30)
                result=dict(await self.observe(),request_id=rid,session_id=self.id,status='ok',action_executed=executed)
            except asyncio.CancelledError:
                self.observation=None
                result={'status':'error','request_id':rid,'code':'ACTION_CANCELLED','retryable':False,'action_executed':executed}
            except Exception as exc:
                result={'status':'error','request_id':rid,'code':str(exc) or type(exc).__name__,'retryable':False,'action_executed':executed}
                if executed:
                    self.observation=None
            finally:
                self.active=None
            self.cache[rid]=(encoded,result)
            return result

    async def cleanup(self):
        errors=[]
        if self.input:
            try: await self.input.close()
            except Exception: errors.append('INPUT_CLEANUP_FAILED')
        if self.capture:
            try: self.capture.close()
            except Exception: errors.append('CAPTURE_CLEANUP_FAILED')
        if self.portal:
            try: await self.portal.stop_stream()
            except Exception: errors.append('PORTAL_CLEANUP_FAILED')
            try: await self.portal.close()
            except Exception: errors.append('PORTAL_DISCONNECT_FAILED')
        for path in self.paths: path.unlink(missing_ok=True)
        return errors

async def serve(output,auto_select=False):
    root=runtime()
    lock=os.open(root/'lock',os.O_RDWR|os.O_CREAT,0o600)
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock);return
    session=Session(root)
    server=None
    socket_path=root/'socket'
    ready=root/'ready.json'
    errors=[]
    writers=set()
    async def client(reader,writer):
        writers.add(writer)
        try:
            data=await asyncio.wait_for(reader.readline(),5)
            request=json.loads(data)
            if not isinstance(request,dict): raise ValueError('INVALID_REQUEST')
            result=await session.request(request)
        except Exception as exc:
            result={'status':'error','code':str(exc) or type(exc).__name__,'retryable':False,'action_executed':False}
        writer.write((json.dumps(result)+'\n').encode());await writer.drain()
        writer.close()
        try: await writer.wait_closed()
        finally: writers.discard(writer)
    async def monitor():
        while not session.done.is_set():
            await asyncio.sleep(1)
            if time.monotonic()-session.last>300:
                session.cancel('idle timeout')
            elif session.input.process.returncode is not None:
                session.cancel('helper interrupted')
    loop=asyncio.get_running_loop()
    for signum in (signal.SIGTERM,signal.SIGINT): loop.add_signal_handler(signum,session.cancel,'interrupted')
    task=None
    try:
        ready.unlink(missing_ok=True)
        (root/'stopped.json').unlink(missing_ok=True)
        for old in root.glob('o-*.png'): old.unlink(missing_ok=True)
        socket_path.unlink(missing_ok=True)
        preparing=asyncio.create_task(session.prepare(output,auto_select))
        cancelled=asyncio.create_task(session.done.wait())
        try:
            completed,_=await asyncio.wait({preparing,cancelled},return_when=asyncio.FIRST_COMPLETED)
            if cancelled in completed:
                preparing.cancel()
                await asyncio.gather(preparing,return_exceptions=True)
                raise RuntimeError('START_CANCELLED')
            first=await preparing
        finally:
            cancelled.cancel()
            await asyncio.gather(cancelled,return_exceptions=True)
        server=await asyncio.start_unix_server(client,path=str(socket_path),limit=131072)
        os.chmod(socket_path,0o600)
        temporary=root/'ready.tmp'
        temporary.write_text(json.dumps(first));os.chmod(temporary,0o600)
        temporary.replace(ready)
        task=asyncio.create_task(monitor())
        await session.done.wait()
    except Exception as exc:
        ready.write_text(json.dumps({'status':'error','code':str(exc) or type(exc).__name__,'action_executed':False,'selector_click_may_have_executed':session.bootstrap_attempted}))
        os.chmod(ready,0o600)
    finally:
        if server:
            server.close()
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        async with session.serial:
            errors=await session.cleanup()
        socket_path.unlink(missing_ok=True)
        fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock)
        if session.started:
            try: await notify('Computer Use has ended' if not errors else 'Computer Use needs attention',('Task interrupted; desktop control has stopped.' if session.stop_reason!='normal' else 'Mouse and keyboard control has stopped.') if not errors else 'Cleanup could not be verified. Check the desktop session.')
            except Exception: errors.append('END_NOTIFICATION_FAILED')
        session.stop_result={'status':'stopped','errors':errors}
        (root/'stopped.json').write_text(json.dumps(session.stop_result))
        session.finished.set()
        if server:
            try:
                await asyncio.wait_for(server.wait_closed(),5)
            except asyncio.TimeoutError:
                for writer in tuple(writers):
                    writer.close()
                await asyncio.wait_for(server.wait_closed(),2)

async def send(request):
    root=runtime()
    try:
        reader,writer=await asyncio.open_unix_connection(str(root/'socket'),limit=131072)
    except (FileNotFoundError,ConnectionRefusedError):
        if request.get('command')=='stop' and (root/'stopped.json').exists():
            return json.loads((root/'stopped.json').read_text())
        raise RuntimeError('SESSION_UNAVAILABLE')
    try:
        writer.write((json.dumps(request)+'\n').encode());await writer.drain()
        return json.loads(await asyncio.wait_for(reader.readline(),40))
    finally:
        writer.close();await writer.wait_closed()

async def start(output,auto_select=False):
    root=runtime()
    if (root/'socket').exists():
        try: return await send({'command':'status'})
        except RuntimeError as exc:
            if str(exc)!='SESSION_UNAVAILABLE': raise
    (root/'ready.json').unlink(missing_ok=True)
    command=[sys.executable,str(Path(__file__).with_name('computer.py')),'_serve']
    if output: command+=['--output',output]
    if auto_select: command+=['--auto-select-single-output']
    owner=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    for _ in range(750):
        if (root/'ready.json').exists(): return json.loads((root/'ready.json').read_text())
        await asyncio.sleep(.1)
    owner.terminate()
    try: await asyncio.to_thread(owner.wait,8)
    except subprocess.TimeoutExpired:
        owner.kill();await asyncio.to_thread(owner.wait)
    return {'status':'error','code':'SESSION_START_TIMEOUT','action_executed':False}
