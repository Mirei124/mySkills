"""Run one fixture-only test action, checking live focus before dispatch."""
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from fixture_guard import require_fixture
from session import send,runtime

async def main():
    action=json.load(sys.stdin)
    state=require_fixture('/tmp/wf-fixture-guarded.json',keyboard=action['type'] in {'keypress','type'})
    first=json.loads((runtime()/'ready.json').read_text())
    last=runtime()/'test-last.json'
    if last.exists():
        saved=json.loads(last.read_text())
        if saved.get('session_id')==first['session_id']: first=saved
    import secrets
    result=await send({'request_id':'test-'+secrets.token_hex(8),'session_id':first['session_id'],'observation_id':first['observation_id'],'action':action})
    print(json.dumps(result))
    if result.get('status')!='ok': raise RuntimeError('FIXTURE_ACTION_FAILED')
    last.write_text(json.dumps(result))
    require_fixture('/tmp/wf-fixture-guarded.json',keyboard=action['type'] in {'keypress','type'})

if __name__=='__main__': asyncio.run(main())
