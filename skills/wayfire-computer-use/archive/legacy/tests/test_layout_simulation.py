"""Contract simulations only; these do not verify compositor mapping."""
import asyncio
from fractions import Fraction
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from input_backend import Input
from outputs import parse_outputs,verify_stream,MappingError

class LayoutSimulationTests(unittest.IsolatedAsyncioTestCase):
    async def test_normalized_pointer_contract_matrix(self):
        # PipeWire frames are assumed display-oriented in this simulation.
        # The compositor handles output binding; the dispatcher emits image
        # coordinates and extents, never offsets in global desktop space.
        cases=0
        for origin in [(0,0),(-1920,0),(1920,-1080)]:
            for scale in [Fraction(1),Fraction(5,4),Fraction(3,2),Fraction(2)]:
                for transform in ['normal','90','180','270','flipped','flipped-90','flipped-180','flipped-270']:
                    width,height=(1080,1920) if transform in {'90','270','flipped-90','flipped-270'} else (1920,1080)
                    logical_w,logical_h=Fraction(width)/scale,Fraction(height)/scale
                    for x,y in [(0,0),(width//2,height//2),(width-1,height-1)]:
                        with self.subTest(origin=origin,scale=str(scale),transform=transform,point=(x,y)):
                            events=[]
                            backend=Input()
                            async def record(command): events.append(command)
                            backend.command=record
                            # Avoid adding 50 ms of toolkit settling to each fake action.
                            async def no_wait(*unused): pass
                            from unittest.mock import patch
                            with patch('input_backend.asyncio.sleep',no_wait):
                                await backend.execute({'type':'move','x':x,'y':y},width,height)
                            _,px,py,ex,ey=events[0].split()
                            simulated=(origin[0]+Fraction(int(px),int(ex))*logical_w,origin[1]+Fraction(int(py),int(ey))*logical_h)
                            expected=(origin[0]+Fraction(x)/scale,origin[1]+Fraction(y)/scale)
                            self.assertEqual(simulated,expected)
                            self.assertEqual(events[-1],'release')
                            cases+=1
        self.assertEqual(cases,288)

    def test_scale_rotation_metadata_is_preserved(self):
        text="\txdg_output_v1\n\t\tname: 'DP-1'\n\t\tlogical_x: -960, logical_y: 0\n\t\tlogical_width: 960, logical_height: 540\ninterface: 'wl_output', version: 4, name: 99\n\tname: DP-1\n\tx: -960, y: 0, scale: 2,\n\tsubpixel_orientation: unknown, output_transform: 180,\n"
        output=parse_outputs(text)[0]
        self.assertEqual(output['scale'],2)
        self.assertEqual(output['transform'],'180')
        self.assertEqual(output['position'],(-960,0))
        verify_stream(output,{'position':[-960,0],'size':[960,540]})
        with self.assertRaisesRegex(MappingError,'OUTPUT_MAPPING_MISMATCH'):
            verify_stream(output,{'position':[0,0],'size':[960,540]})
