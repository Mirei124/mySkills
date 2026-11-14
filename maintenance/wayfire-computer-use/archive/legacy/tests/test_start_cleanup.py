import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import session
from portal import Portal

class StartCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_start_reaps_preparing_owner(self):
        owner=Mock()
        owner.poll.return_value=None
        owner.wait.return_value=0
        with tempfile.TemporaryDirectory() as directory:
            with patch('session.runtime',return_value=Path(directory)),patch('session.subprocess.Popen',return_value=owner):
                task=asyncio.create_task(session.start(None))
                await asyncio.sleep(.01)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
        owner.terminate.assert_called_once()
        owner.wait.assert_called_once_with(8)
    async def test_ready_owner_is_not_terminated(self):
        owner=Mock()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def spawn(*args,**kwargs):
                (root/'ready.json').write_text('{"status":"ready"}')
                return owner
            with patch('session.runtime',return_value=root),patch('session.subprocess.Popen',side_effect=spawn):
                self.assertEqual(await session.start(None),{'status':'ready'})
        owner.terminate.assert_not_called()
        owner.wait.assert_not_called()
    async def test_portal_call_has_a_deadline(self):
        portal=Portal()
        cancelled=asyncio.Event()
        async def call(message):
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        portal.bus=type('Bus',(),{'call':staticmethod(call)})()
        with self.assertRaises(asyncio.TimeoutError): await portal.call(object(),timeout=.01)
        self.assertTrue(cancelled.is_set())
