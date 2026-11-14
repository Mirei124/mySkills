import asyncio
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).parents[1]/'wayfire-computer-use/scripts'))
from selector import click_once

class SelectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_click_after_notice_for_new_selector(self):
        events=[]
        async def notice(): events.append('notice')
        async def spawn(*args,**kwargs):
            events.append(args)
            return SimpleNamespace(wait=AsyncMock(return_value=0),returncode=0)
        with patch('selector.selectors',return_value={100,200}),patch('selector.asyncio.create_subprocess_exec',spawn):
            await click_once({100},notice)
        self.assertEqual(events,['notice',('wlrctl','pointer','click','left')])
    async def test_ambiguous_selector_never_clicks(self):
        with patch('selector.selectors',return_value={100,200}),patch('selector.asyncio.create_subprocess_exec',new=AsyncMock()) as spawn:
            with self.assertRaisesRegex(RuntimeError,'AMBIGUOUS_PORTAL_SELECTOR'):
                await click_once(set(),AsyncMock())
            spawn.assert_not_awaited()
    async def test_notification_failure_prevents_click(self):
        with patch('selector.selectors',return_value={100}),patch('selector.asyncio.create_subprocess_exec',new=AsyncMock()) as spawn:
            with self.assertRaisesRegex(RuntimeError,'NOTIFICATION_FAILED'):
                await click_once(set(),AsyncMock(side_effect=RuntimeError('NOTIFICATION_FAILED')))
            spawn.assert_not_awaited()
