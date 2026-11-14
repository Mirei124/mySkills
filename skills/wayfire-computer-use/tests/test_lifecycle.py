from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from session import Session

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_notification_failure_never_executes_input(self):
        events=[]
        geometry=[{'name':'test','position':(0,0),'size':(100,100)}]
        portal=SimpleNamespace(output=geometry[0],start_stream=AsyncMock(return_value={'streams':[[1,{}]]}),stop_stream=AsyncMock(),close=AsyncMock())
        portal_class=SimpleNamespace(connect=AsyncMock(return_value=portal))
        backend=SimpleNamespace(start=AsyncMock(),execute=AsyncMock(),close=AsyncMock())
        backend.start.return_value=backend
        capture=SimpleNamespace(close=lambda:events.append('capture_closed'))
        with tempfile.TemporaryDirectory() as directory:
            session=Session(Path(directory))
            session.outputs=AsyncMock(return_value=geometry)
            session.observe=AsyncMock(return_value={'width':100,'height':100})
            with patch('session.Portal',return_value=portal_class),patch('session.Input',return_value=backend),patch('session.Capture',return_value=capture),patch('session.notify',new=AsyncMock(side_effect=RuntimeError('NOTIFICATION_FAILED'))):
                with self.assertRaisesRegex(RuntimeError,'NOTIFICATION_FAILED'):
                    await session.prepare(None)
                self.assertFalse(session.started)
                backend.execute.assert_not_awaited()
                self.assertEqual(await session.cleanup(),[])
                backend.close.assert_awaited_once()
                portal.stop_stream.assert_awaited_once()
    async def test_cleanup_continues_after_input_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            session=Session(Path(directory))
            session.input=SimpleNamespace(close=AsyncMock(side_effect=RuntimeError('FAIL')))
            session.portal=SimpleNamespace(stop_stream=AsyncMock(),close=AsyncMock())
            errors=await session.cleanup()
            self.assertEqual(errors,['INPUT_CLEANUP_FAILED'])
            session.portal.stop_stream.assert_awaited_once()
            session.portal.close.assert_awaited_once()
