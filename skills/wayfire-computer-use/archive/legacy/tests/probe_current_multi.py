"""Explicit HEADLESS-8-only integration harness; not a production capability."""
import asyncio
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import session
from portal import Portal
from selector import selectors
from input_backend import Input

original=Portal.start_stream
async def start_stream(self,output_name=None,auto_select=False,before_click=None):
    if output_name!='HEADLESS-8': raise RuntimeError('TEST_OUTPUT_REQUIRED')
    existing=selectors()
    async def choose():
        while True:
            new=selectors()-existing
            if len(new)>1: raise RuntimeError('AMBIGUOUS_PORTAL_SELECTOR')
            if new: break
            await asyncio.sleep(.05)
        await before_click()
        backend=None
        try:
            backend=await Input().start('HEADLESS-8')
            if selectors()-existing!=new: raise RuntimeError('PORTAL_SELECTOR_DISAPPEARED')
            await backend.command('move 960 540 1920 1080')
            await asyncio.sleep(.1)
            if selectors()-existing!=new: raise RuntimeError('PORTAL_SELECTOR_DISAPPEARED')
            process=await asyncio.create_subprocess_exec('wlrctl','pointer','click','left')
            if await asyncio.wait_for(process.wait(),3): raise RuntimeError('PORTAL_SELECTOR_CLICK_FAILED')
        finally:
            if backend: await backend.close()
    chooser=asyncio.create_task(choose())
    try:
        return await original(self,output_name,False,before_click)
    finally:
        chooser.cancel()
        results=await asyncio.gather(chooser,return_exceptions=True)
        if isinstance(results[0],Exception): raise results[0]

class TestSession(session.Session):
    allow_unverified_multi=True

if __name__=='__main__':
    session.Session=TestSession
    Portal.start_stream=start_stream
    asyncio.run(session.serve('HEADLESS-8'))
