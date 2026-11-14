"""Output selection and portal logical-geometry checks."""
import re

class MappingError(ValueError):
    pass

def parse_outputs(text):
    outputs = []
    for block in text.split('\txdg_output_v1\n')[1:]:
        block = '\n' + block
        block = block.split('\ninterface:')[0]
        name = re.search(r"\n\s*name: '([^']+)'", block)
        position = re.search(r'logical_x: (-?\d+), logical_y: (-?\d+)', block)
        size = re.search(r'logical_width: (\d+), logical_height: (\d+)', block)
        if not (name and position and size):
            raise MappingError('OUTPUT_GEOMETRY_UNAVAILABLE')
        outputs.append({'name':name[1], 'position':tuple(map(int,position.groups())), 'size':tuple(map(int,size.groups()))})
    if not outputs:
        raise MappingError('OUTPUT_GEOMETRY_UNAVAILABLE')
    if len({o['name'] for o in outputs}) != len(outputs):
        raise MappingError('AMBIGUOUS_OUTPUT_NAMES')
    # wl_output metadata must participate in layout invalidation even when
    # xdg-output logical bounds do not change (for example a 180-degree turn).
    for block in re.split(r"interface: 'wl_output',[^\n]*\n", text)[1:]:
        block='\n'+block.split('\ninterface:')[0]
        name=re.search(r"\n\s*name: ([^\n]+)",block)
        scale=re.search(r'scale: (\d+)',block)
        transform=re.search(r'output_transform: ([^,\n]+)',block)
        if not name: continue
        for output in outputs:
            if output['name']==name[1].strip():
                if scale: output['scale']=int(scale[1])
                if transform: output['transform']=transform[1].strip()
    return outputs

def select_output(outputs, name=None):
    if name is None:
        if len(outputs) != 1:
            raise MappingError('OUTPUT_CONFIRMATION_REQUIRED')
        return outputs[0]
    matches = [o for o in outputs if o['name'] == name]
    if len(matches) != 1:
        raise MappingError('UNKNOWN_OUTPUT')
    return matches[0]

def verify_stream(output, properties):
    def unpack(value):
        return value.value if hasattr(value,'value') else value
    for field in ('position','size'):
        if field not in properties or tuple(unpack(properties[field])) != output[field]:
            raise MappingError('OUTPUT_MAPPING_MISMATCH')
    return output
