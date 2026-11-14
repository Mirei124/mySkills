import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'wayfire-computer-use/scripts'))
from outputs import select_output,verify_stream,MappingError,parse_outputs

class OutputsTests(unittest.TestCase):
    def setUp(self):
        self.output={'name':'eDP-1','position':(-1920,0),'size':(1920,1080)}
    def test_single_automatic(self):
        self.assertEqual(select_output([self.output]),self.output)
    def test_multiple_requires_choice(self):
        with self.assertRaisesRegex(MappingError,'OUTPUT_CONFIRMATION_REQUIRED'):
            select_output([self.output,dict(self.output,name='DP-1')])
        self.assertEqual(select_output([self.output], 'eDP-1'),self.output)
    def test_geometry_must_match(self):
        verify_stream(self.output,self.output)
        with self.assertRaisesRegex(MappingError,'OUTPUT_MAPPING_MISMATCH'):
            verify_stream(self.output,dict(self.output,position=(0,0)))
    def test_parse_negative_origin(self):
        text="\txdg_output_v1\n\t\tname: 'eDP-1'\n\t\tlogical_x: -1920, logical_y: 0\n\t\tlogical_width: 1920, logical_height: 1080\ninterface: 'wl_output'"
        self.assertEqual(parse_outputs(text),[self.output])
