import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fixture_guard import require_fixture

class FixtureGuardTests(unittest.TestCase):
    def test_missing_state_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError): require_fixture(Path(directory)/'missing.json')
    def test_exited_process_blocks_before_focus_query(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            path.write_text(json.dumps({'pid':12345}))
            with patch('fixture_guard.os.kill',side_effect=ProcessLookupError),patch('fixture_guard.subprocess.run') as run:
                with self.assertRaises(ProcessLookupError): require_fixture(path)
                run.assert_not_called()
