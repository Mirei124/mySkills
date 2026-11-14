import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).parents[1]/'wayfire-computer-use/scripts'))
from session import Session

class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.session=Session(Path(self.directory.name))
        self.session.geometry=[{'name':'test'}]
        self.session.width=self.session.height=100
        self.session.observation='old'
        self.session.outputs=AsyncMock(return_value=self.session.geometry)
        self.session.input=type('Backend',(),{'execute':AsyncMock()})()
        async def observe():
            self.session.observation='new'
            return {'observation_id':'new'}
        self.session.observe=AsyncMock(side_effect=observe)
    def request(self,action=None):
        return {'request_id':'r1','session_id':self.session.id,'observation_id':'old','action':action or {'type':'click','x':10,'y':10,'button':'left'}}
    async def test_duplicate_does_not_replay(self):
        request=self.request()
        first=await self.session.request(request)
        self.assertEqual(first,await self.session.request(request))
        self.session.input.execute.assert_awaited_once()
    async def test_capture_failure_preserves_execution_and_dedup(self):
        self.session.observe=AsyncMock(side_effect=RuntimeError('CAPTURE_FAILED'))
        request=self.request()
        first=await self.session.request(request)
        self.assertTrue(first['action_executed'])
        self.assertEqual(first['code'],'CAPTURE_FAILED')
        self.assertIsNone(self.session.observation)
        self.assertEqual(first,await self.session.request(request))
        self.session.input.execute.assert_awaited_once()
    async def test_layout_change_prevents_input(self):
        self.session.outputs=AsyncMock(return_value=[])
        result=await self.session.request(self.request())
        self.assertEqual(result['code'],'LAYOUT_CHANGED')
        self.assertFalse(result['action_executed'])
        self.session.input.execute.assert_not_awaited()
    async def test_stale_observation_prevents_input(self):
        request=self.request();request['observation_id']='wrong'
        result=await self.session.request(request)
        self.assertEqual(result['code'],'STALE_OBSERVATION')
        self.session.input.execute.assert_not_awaited()
    async def test_screenshot_only_captures_once(self):
        await self.session.request(self.request({'type':'screenshot'}))
        self.session.observe.assert_awaited_once()
        self.session.input.execute.assert_not_awaited()

    async def test_stop_cancels_action_before_cleanup_ack(self):
        entered=asyncio.Event()
        released=asyncio.Event()
        async def execute(*args):
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                released.set()
        self.session.input.execute=execute
        action=asyncio.create_task(self.session.request(self.request()))
        await entered.wait()
        stop=asyncio.create_task(self.session.request({'command':'stop'}))
        await asyncio.wait_for(released.wait(),.5)
        self.assertFalse(stop.done())
        result=await asyncio.wait_for(action,.5)
        self.assertEqual(result['code'],'ACTION_CANCELLED')
        self.assertTrue(result['action_executed'])
        self.session.stop_result={'status':'stopped','errors':[]}
        self.session.finished.set()
        self.assertEqual(await asyncio.wait_for(stop,.5),self.session.stop_result)

    async def test_repeated_stop_does_not_interrupt_release(self):
        entered=asyncio.Event()
        releasing=asyncio.Event()
        release_complete=asyncio.Event()
        async def execute(*args):
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                releasing.set()
                await release_complete.wait()
        self.session.input.execute=execute
        action=asyncio.create_task(self.session.request(self.request()))
        await entered.wait()
        first=asyncio.create_task(self.session.request({'command':'stop'}))
        await releasing.wait()
        second=asyncio.create_task(self.session.request({'command':'stop'}))
        await asyncio.sleep(0)
        self.assertFalse(action.done())
        release_complete.set()
        await asyncio.wait_for(action,.5)
        self.session.stop_result={'status':'stopped','errors':[]}
        self.session.finished.set()
        self.assertEqual(await first,await second)

    async def test_stop_during_discovery_prevents_dispatch(self):
        entered=asyncio.Event()
        async def discover():
            entered.set();await asyncio.Event().wait()
        self.session.outputs=discover
        action=asyncio.create_task(self.session.request(self.request()))
        await entered.wait()
        stop=asyncio.create_task(self.session.request({'command':'stop'}))
        result=await asyncio.wait_for(action,.5)
        self.assertEqual(result['code'],'ACTION_CANCELLED')
        self.assertFalse(result['action_executed'])
        self.session.input.execute.assert_not_awaited()
        self.session.finished.set()
        await stop

    async def test_stop_during_capture_reports_prior_execution(self):
        entered=asyncio.Event()
        async def observe():
            entered.set();await asyncio.Event().wait()
        self.session.observe=observe
        action=asyncio.create_task(self.session.request(self.request()))
        await entered.wait()
        stop=asyncio.create_task(self.session.request({'command':'stop'}))
        result=await asyncio.wait_for(action,.5)
        self.assertEqual(result['code'],'ACTION_CANCELLED')
        self.assertTrue(result['action_executed'])
        self.session.finished.set()
        await stop
