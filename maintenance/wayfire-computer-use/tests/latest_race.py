"""Interpose between two normal CLI connections to force an observation race."""
import json
import socket
import subprocess
from pathlib import Path


def verify_latest_race(binary, env, root, observed):
    owner_dir = Path(observed["screenshot_path"]).parent
    runtime = root / "race"
    proxy_dir = runtime / owner_dir.name
    proxy_dir.mkdir(mode=0o700, parents=True)
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(proxy_dir / "socket"))
        listener.listen()
        listener.settimeout(8)
        with subprocess.Popen(
            [binary, "act", "--latest"], env={**env, "XDG_RUNTIME_DIR": str(runtime)},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        ) as pending:
            pending.stdin.write(json.dumps({"type":"click","button":"left","x":1,"y":1}))
            pending.stdin.close()
            for phase in ("status", "action"):
                peer, _ = listener.accept()
                with peer, peer.makefile("rb") as incoming, socket.socket(socket.AF_UNIX) as owner:
                    owner.settimeout(8)
                    request = incoming.readline()
                    owner.connect(str(owner_dir / "socket"))
                    owner.sendall(request)
                    with owner.makefile("rb") as reply:
                        response = reply.readline()
                    if phase == "status":
                        assert json.loads(request) == {"command":"status"}
                        assert json.loads(response)["observation_id"] == observed["observation_id"]
                        newer = subprocess.run(
                            [binary, "act", "--latest"], input='{"type":"screenshot"}',
                            capture_output=True, text=True, env=env, timeout=12, check=True,
                        )
                        advanced = json.loads(newer.stdout)
                        assert advanced["observation_id"] != observed["observation_id"]
                    peer.sendall(response)
            result = json.loads(pending.stdout.readline())
            assert pending.wait(timeout=5) != 0
            assert result["code"] == "STALE_OBSERVATION" and result["action_executed"] is False
            assert result["resolved_envelope"]["observation_id"] == observed["observation_id"]
            return advanced
