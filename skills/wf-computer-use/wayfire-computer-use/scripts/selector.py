"""Explicitly enabled, single-output Portal selector bootstrap click."""
import asyncio
import os
from pathlib import Path


def selectors():
    found=set()
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        try:
            if entry.stat().st_uid!=os.getuid(): continue
            argv=(entry/'cmdline').read_bytes().split(b'\0')
            if argv and Path(os.fsdecode(argv[0])).name=='slurp' and b'Monitor: %o' in argv and b'-or' in argv:
                found.add(int(entry.name))
        except (FileNotFoundError,PermissionError,ProcessLookupError): pass
    return found

async def click_once(existing,before_click):
    while True:
        candidates=selectors()-existing
        if len(candidates)>1: raise RuntimeError('AMBIGUOUS_PORTAL_SELECTOR')
        if candidates:
            # Process discovery is not an input-grab acknowledgement. Allow setup,
            # then check again immediately before the one authorized click.
            await asyncio.sleep(.2)
            if selectors()-existing!=candidates: continue
            await before_click()
            if selectors()-existing!=candidates: raise RuntimeError('PORTAL_SELECTOR_DISAPPEARED')
            process=await asyncio.create_subprocess_exec('wlrctl','pointer','click','left',stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
            try: code=await asyncio.wait_for(process.wait(),3)
            except BaseException:
                if process.returncode is None: process.kill();await process.wait()
                raise
            if code: raise RuntimeError('PORTAL_SELECTOR_CLICK_FAILED')
            return
        await asyncio.sleep(.05)
