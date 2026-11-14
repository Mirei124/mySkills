import importlib.util
import pathlib
import unittest
spec = importlib.util.spec_from_file_location('computer', pathlib.Path(__file__).parents[1] / 'scripts/computer.py')
computer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(computer)

class ContractTests(unittest.TestCase):
    def test_rejects_invalid_actions(self):
        for action in ({'type':'shell'}, {'type':'screenshot','x':1}, {'type':'move','x':True,'y':2}, {'type':'drag','path':[]}, {'type':'click','x':1,'y':2,'button':'unknown'}):
            with self.subTest(action=action), self.assertRaises(ValueError):
                computer.validate(action)

    def test_accepts_draft_actions(self):
        for action in ({'type':'screenshot'}, {'type':'move','x':1,'y':2}, {'type':'type','text':'你好'}, {'type':'keypress','keys':['CTRL','A']}):
            self.assertEqual(computer.validate(action),action)

if __name__ == '__main__':
    unittest.main()
