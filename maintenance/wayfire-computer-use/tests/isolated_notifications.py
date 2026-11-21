"""Notification sink on an isolated test bus; never displays real notifications."""
import asyncio
import json
import os
from pathlib import Path
from dbus_next.errors import DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface,method,dbus_property
from dbus_next.constants import PropertyAccess

class Notifications(ServiceInterface):
    def __init__(self): super().__init__('org.freedesktop.Notifications')
    @method()
    async def Notify(self,app:'s',replaces:'u',icon:'s',summary:'s',body:'s',actions:'as',hints:'a{sv}',expire:'i')->'u':
        print(json.dumps({'summary':summary,'body':body}),flush=True)
        control=os.environ.get('WF_NOTIFY_FAILURE_FILE')
        mode=Path(control).read_text() if control and Path(control).exists() else ''
        if (mode=='start' and summary=='Computer Use is preparing desktop control') or (mode=='end' and summary in {'Computer Use has ended','Computer Use needs attention'}):
            raise DBusError('org.example.IsolatedNotificationFailure','Injected notification failure')
        if mode=='delay-end' and summary in {'Computer Use has ended','Computer Use needs attention'}:
            await asyncio.sleep(.5)
        return 1

class LockSession(ServiceInterface):
    def __init__(self): super().__init__('org.freedesktop.login1.Session')

    @dbus_property(access=PropertyAccess.READ)
    def LockedHint(self)->'b':
        return Path(os.environ['XDG_RUNTIME_DIR'],'locked').exists()

class LoginManager(ServiceInterface):
    def __init__(self): super().__init__('org.freedesktop.login1.Manager')

    @method()
    def GetSessionByPID(self,pid:'u')->'o':
        return '/org/freedesktop/login1/session/test'

async def main():
    bus=await MessageBus().connect()
    session=LockSession()
    bus.export('/org/freedesktop/login1/session/self',session)
    bus.export('/org/freedesktop/login1/session/test',session)
    bus.export('/org/freedesktop/login1',LoginManager())
    await bus.request_name('org.freedesktop.login1')
    bus.export('/org/freedesktop/Notifications',Notifications())
    await bus.request_name('org.freedesktop.Notifications')
    previous=False
    while True:
        current=session.LockedHint
        if current != previous:
            session.emit_properties_changed({'LockedHint':current})
            previous=current
        await asyncio.sleep(.05)

if __name__=='__main__':asyncio.run(main())
