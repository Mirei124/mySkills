import asyncio
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'wayfire-computer-use/scripts'))
from input_backend import Input,key,character

class InputTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend=Input()
        self.events=[]
        async def command(text): self.events.append(text)
        self.backend.command=command
    async def test_drag_holds_same_button_until_last_point(self):
        await self.backend.execute({'type':'drag','path':[{'x':1,'y':2},{'x':30,'y':40}]},100,100)
        self.assertEqual(self.events,['move 1 2 100 100','button 272 1','move 30 40 100 100','button 272 0','release'])
    async def test_failure_releases_held_input(self):
        async def command(text):
            self.events.append(text)
            if text.startswith('move'): raise RuntimeError('DISCONNECTED')
        self.backend.command=command
        with self.assertRaisesRegex(RuntimeError,'DISCONNECTED'):
            await self.backend.execute({'type':'move','x':1,'y':2,'keys':['CTRL']},100,100)
        self.assertEqual(self.events[-1],'release')
    async def test_invalid_path_has_no_input(self):
        with self.assertRaisesRegex(ValueError,'COORDINATE_OUT_OF_BOUNDS'):
            await self.backend.execute({'type':'drag','path':[{'x':1,'y':2},{'x':100,'y':2}]},100,100)
        self.assertEqual(self.events,[])
    async def test_scroll_positions_before_axis(self):
        await self.backend.execute({'type':'scroll','x':2,'y':3,'scroll_x':-20,'scroll_y':40},100,100)
        self.assertEqual(self.events,['move 2 3 100 100','axis 0 4.0','axis 1 -2.0','release'])
    async def test_cancellation_releases_drag(self):
        moved=asyncio.Event()
        async def command(text):
            self.events.append(text)
            if text=='move 30 40 100 100':
                moved.set();await asyncio.Event().wait()
        self.backend.command=command
        task=asyncio.create_task(self.backend.execute({'type':'drag','path':[{'x':1,'y':2},{'x':30,'y':40}]},100,100))
        await moved.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(self.events[-1],'release')
    def test_aliases_and_unicode(self):
        self.assertEqual(key('CONTROL'),key('CTRL'))
        self.assertEqual(character('你'),(-ord('你'),0))
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_KEY'): key('CMD')
