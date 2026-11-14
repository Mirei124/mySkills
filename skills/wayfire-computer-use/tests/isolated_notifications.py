"""Notification sink on an isolated test bus; never displays real notifications."""
import asyncio
import json
import os
from pathlib import Path
from dbus_next.errors import DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface,method

class Notifications(ServiceInterface):
    def __init__(self): super().__init__('org.freedesktop.Notifications')
    @method()
    def Notify(self,app:'s',replaces:'u',icon:'s',summary:'s',body:'s',actions:'as',hints:'a{sv}',expire:'i')->'u':
        print(json.dumps({'summary':summary,'body':body}),flush=True)
        control=os.environ.get('WF_NOTIFY_FAILURE_FILE')
        mode=Path(control).read_text() if control and Path(control).exists() else ''
        if (mode=='start' and summary=='Computer Use is preparing desktop control') or (mode=='end' and summary in {'Computer Use has ended','Computer Use needs attention'}):
            raise DBusError('org.example.IsolatedNotificationFailure','Injected notification failure')
        return 1

async def main():
    bus=await MessageBus().connect()
    bus.export('/org/freedesktop/Notifications',Notifications())
    await bus.request_name('org.freedesktop.Notifications')
    await asyncio.Event().wait()

if __name__=='__main__':asyncio.run(main())
