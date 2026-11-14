"""Run one guarded fixture action through the Rust CLI (development test only)."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from fixture_guard import require_fixture

root=Path(__file__).resolve().parents[1]
binary=Path(os.environ.get('WAYFIRE_COMPUTER_USE_BIN',str(root/'target/debug/wayfire-computer-use')))
action=json.load(sys.stdin)
require_fixture('/tmp/wf-fixture-guarded.json',keyboard=action['type'] in {'keypress','type'})
status=json.loads(subprocess.check_output([str(binary),'status'],text=True))
request={'request_id':'test-'+secrets.token_hex(8),'session_id':status['session_id'],'observation_id':status['observation_id'],'action':action}
result=subprocess.run([str(binary),'act'],input=json.dumps(request),capture_output=True,text=True,timeout=40)
print(result.stdout,end='')
if result.returncode:raise SystemExit(result.returncode)
require_fixture('/tmp/wf-fixture-guarded.json',keyboard=action['type'] in {'keypress','type'})
