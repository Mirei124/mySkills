"""Persistent D-Bus portal client. No input or permission bypasses."""
import asyncio
import secrets
from dbus_next import BusType, Message, MessageType, Variant
from dbus_next.aio import MessageBus

class PortalError(RuntimeError):
    pass

class Portal:
    destination = 'org.freedesktop.portal.Desktop'
    path = '/org/freedesktop/portal/desktop'

    async def connect(self):
        self.bus = await MessageBus(bus_type=BusType.SESSION, negotiate_unix_fd=True).connect()
        return self

    async def call(self, message, timeout=5):
        return await asyncio.wait_for(self.bus.call(message),timeout)

    async def request(self, interface, method, signature, body, timeout=60):
        token = 'wf_' + secrets.token_hex(12)
        body[-1]['handle_token'] = Variant('s', token)
        sender = self.bus.unique_name[1:].replace('.', '_')
        path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
        future = asyncio.get_running_loop().create_future()
        def receive(message):
            if message.message_type == MessageType.SIGNAL and message.path == path and message.interface == 'org.freedesktop.portal.Request' and message.member == 'Response' and not future.done():
                future.set_result(message.body)
        rule = f"type='signal',interface='org.freedesktop.portal.Request',member='Response',path='{path}'"
        match = await self.call(Message(destination='org.freedesktop.DBus', path='/org/freedesktop/DBus', interface='org.freedesktop.DBus', member='AddMatch', signature='s', body=[rule]))
        if match.message_type == MessageType.ERROR:
            raise PortalError('PORTAL_SIGNAL_SUBSCRIPTION_FAILED')
        self.bus.add_message_handler(receive)
        try:
            reply = await self.call(Message(destination=self.destination, path=self.path, interface=interface, member=method, signature=signature, body=body),timeout)
            if reply.message_type == MessageType.ERROR:
                raise PortalError(f'PORTAL_UNAVAILABLE: {reply.error_name}')
            if reply.body != [path]:
                raise PortalError('PORTAL_REQUEST_PATH_MISMATCH')
            code, result = await asyncio.wait_for(future, timeout)
            if code:
                raise PortalError('CAPTURE_CANCELLED' if code == 1 else 'CAPTURE_FAILED')
            return {key: value.value for key, value in result.items()}
        except (asyncio.TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(self.bus.call(Message(destination=self.destination, path=path, interface='org.freedesktop.portal.Request', member='Close')),3)
            raise
        finally:
            self.bus.remove_message_handler(receive)
            await self.call(Message(destination='org.freedesktop.DBus', path='/org/freedesktop/DBus', interface='org.freedesktop.DBus', member='RemoveMatch', signature='s', body=[rule]))

    async def screenshot(self):
        return await self.request('org.freedesktop.portal.Screenshot', 'Screenshot', 'sa{sv}', ['', {'interactive': Variant('b', False)}])

    async def close(self):
        self.bus.disconnect()

    async def start_stream(self, output_name=None, auto_select=False, before_click=None):
        """Ask the user to select exactly one monitor and retain its portal session."""
        from outputs import parse_outputs, select_output, verify_stream
        process = await asyncio.create_subprocess_exec('wayland-info', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 8)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode:
            raise PortalError('OUTPUT_DISCOVERY_FAILED')
        outputs=parse_outputs(stdout.decode())
        self.output = select_output(outputs, output_name)
        if auto_select and len(outputs)!=1:
            raise PortalError('OUTPUT_CONFIRMATION_REQUIRED')
        selector=None
        if auto_select:
            from selector import selectors,click_once
            if before_click is None: raise PortalError('SELECTOR_NOTIFICATION_REQUIRED')
            baseline=selectors()
        created = await self.request('org.freedesktop.portal.ScreenCast', 'CreateSession', 'a{sv}', [{'session_handle_token': Variant('s', 'wf_' + secrets.token_hex(12))}])
        self.session = created['session_handle']
        try:
            if auto_select:
                selector=asyncio.create_task(click_once(baseline,before_click))
            await self.request('org.freedesktop.portal.ScreenCast', 'SelectSources', 'oa{sv}', [self.session, {'types': Variant('u', 1), 'multiple': Variant('b', False), 'cursor_mode': Variant('u', 1)}])
            started = await self.request('org.freedesktop.portal.ScreenCast', 'Start', 'osa{sv}', [self.session, '', {}])
            if len(started.get('streams', [])) != 1:
                raise PortalError('OUTPUT_MAPPING_UNAVAILABLE')
            verify_stream(self.output, started['streams'][0][1])
            reply = await self.call(Message(destination=self.destination, path=self.path, interface='org.freedesktop.portal.ScreenCast', member='OpenPipeWireRemote', signature='oa{sv}', body=[self.session, {}]))
            if reply.message_type == MessageType.ERROR or not reply.unix_fds:
                raise PortalError('PIPEWIRE_REMOTE_UNAVAILABLE')
            self.remote_fd = reply.unix_fds[reply.body[0]]
            return started
        except BaseException:
            await self.stop_stream()
            raise
        finally:
            if selector:
                selector.cancel()
                result=await asyncio.gather(selector,return_exceptions=True)
                if isinstance(result[0],Exception): raise result[0]

    async def stop_stream(self):
        import os
        if getattr(self, 'session', None):
            try:
                await asyncio.wait_for(self.bus.call(Message(destination=self.destination, path=self.session, interface='org.freedesktop.portal.Session', member='Close')),3)
            finally:
                self.session = None
                if getattr(self, 'remote_fd', None) is not None:
                    os.close(self.remote_fd)
                    self.remote_fd = None
