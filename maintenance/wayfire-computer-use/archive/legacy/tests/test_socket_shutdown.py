"""Exercise the actual server and transport shutdown, without a desktop."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import session

class SocketShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_ack_precedes_client_transport_close(self):
        events=[]
        async def prepare(owner,output,auto_select=False):
            owner.started=True
            return {'status':'ready'}
        async def cleanup(owner):
            events.append('cleanup')
            return []
        async def notify(*args): events.append('notification')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('session.runtime',return_value=root),patch.object(session.Session,'prepare',prepare),patch.object(session.Session,'cleanup',cleanup),patch('session.notify',notify):
                server=asyncio.create_task(session.serve(None))
                for _ in range(100):
                    if (root/'ready.json').exists(): break
                    await asyncio.sleep(.005)
                self.assertTrue((root/'ready.json').exists())
                reader,writer=await asyncio.open_unix_connection(str(root/'socket'))
                try:
                    writer.write(b'{"command":"stop"}\n');await writer.drain()
                    result=json.loads(await asyncio.wait_for(reader.readline(),1))
                    self.assertEqual(result,{'status':'stopped','errors':[]})
                    self.assertEqual(events,['cleanup','notification'])
                finally:
                    writer.close();await writer.wait_closed()
                    await asyncio.wait_for(server,1)

    async def test_cancel_interrupts_preparation_and_cleans(self):
        entered=asyncio.Event()
        owners=[]
        events=[]
        async def prepare(owner,output,auto_select=False):
            owners.append(owner);entered.set()
            await asyncio.Event().wait()
        async def cleanup(owner): events.append('cleanup');return []
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('session.runtime',return_value=root),patch.object(session.Session,'prepare',prepare),patch.object(session.Session,'cleanup',cleanup):
                server=asyncio.create_task(session.serve(None))
                await entered.wait()
                owners[0].cancel('interrupted')
                await asyncio.wait_for(server,1)
                self.assertEqual(events,['cleanup'])
                self.assertEqual(json.loads((root/'ready.json').read_text())['code'],'START_CANCELLED')
