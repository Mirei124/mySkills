"""Serialized action dispatch over a persistent native helper."""
import asyncio
from pathlib import Path

KEYS={'CTRL':(29,4),'SHIFT':(42,1),'ALT':(56,8),'SUPER':(125,64),'ENTER':(28,0),'TAB':(15,0),'ESC':(1,0),'BACKSPACE':(14,0),'DELETE':(111,0),'LEFT':(105,0),'RIGHT':(106,0),'UP':(103,0),'DOWN':(108,0),'HOME':(102,0),'END':(107,0),'PAGEUP':(104,0),'PAGEDOWN':(109,0),'SPACE':(57,0)}
for letters,codes in [('qwertyuiop',range(16,26)),('asdfghjkl',range(30,39)),('zxcvbnm',range(44,51)),('1234567890',range(2,12))]:
    KEYS.update({letter.upper():(code,0) for letter,code in zip(letters,codes)})
KEYS.update({f'F{i}':(58+i if i<=10 else 76+i,0) for i in range(1,13)})
ALIASES={'CONTROL':'CTRL','ESCAPE':'ESC','RETURN':'ENTER','ARROWLEFT':'LEFT','ARROWRIGHT':'RIGHT','ARROWUP':'UP','ARROWDOWN':'DOWN','META':'SUPER'}

def key(name):
    name=ALIASES.get(name.upper(),name.upper())
    if name not in KEYS:
        raise ValueError('UNSUPPORTED_KEY')
    return KEYS[name]

def character(char):
    if char in '\n\t ': return key({'\n':'ENTER','\t':'TAB',' ':'SPACE'}[char])
    if char.isascii() and char.isalnum():
        code,_=key(char)
        return code,1 if char.isupper() else 0
    plain="-=[];'`,./\\"
    shifted='_+{}:"~<>?|'
    codes=[12,13,26,27,39,40,41,51,52,53,43]
    if char in plain: return codes[plain.index(char)],0
    if char in shifted: return codes[shifted.index(char)],1
    if char in '!@#$%^&*()': return [2,3,4,5,6,7,8,9,10,11]['!@#$%^&*()'.index(char)],1
    if 0x20 <= ord(char) <= 0x10ffff and not 0xd800 <= ord(char) <= 0xdfff:
        return -ord(char),0
    raise ValueError('UNSUPPORTED_UNICODE')

class Input:
    async def start(self,output=None):
        executable=Path(__file__).resolve().parents[1]/'native/build/input-helper'
        arguments=['--output',output] if output else []
        self.process=await asyncio.create_subprocess_exec(str(executable),*arguments,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            if await asyncio.wait_for(self.process.stdout.readline(),5) != b'READY\n':
                raise RuntimeError('INPUT_START_FAILED')
        except BaseException:
            await self.close()
            raise
        # A compositor roundtrip does not acknowledge toolkit focus processing.
        await asyncio.sleep(.15)
        return self
    async def command(self,text):
        self.process.stdin.write((text+'\n').encode())
        await self.process.stdin.drain()
        if await asyncio.wait_for(self.process.stdout.readline(),2) != b'OK\n':
            raise RuntimeError('INPUT_FAILED')
    async def execute(self,action,width,height):
        from computer import validate
        validate(action)
        kind=action['type']
        points=action.get('path',[]) if kind=='drag' else [action] if 'x' in action else []
        if any(not 0<=p['x']<width or not 0<=p['y']<height for p in points):
            raise ValueError('COORDINATE_OUT_OF_BOUNDS')
        held=[key(k) for k in (action.get('keys') or [])]
        text=[character(c) for c in action['text']] if kind=='type' else []
        async def move(p): await self.command(f"move {p['x']} {p['y']} {width} {height}")
        async def button(code,state): await self.command(f'button {code} {state}')
        try:
            mask=0
            for code,mod in held:
                await self.command(f'key {code} 1');mask|=mod
                await self.command(f'modifiers {mask}')
            if kind=='keypress': return
            if kind=='type':
                for code,mod in text:
                    if code < 0:
                        await self.command(f'unicode {-code}')
                        continue
                    await self.command(f'modifiers {mod}')
                    await self.command(f'key {code} 1');await self.command(f'key {code} 0')
                    await self.command('modifiers 0')
            elif kind=='drag':
                await move(points[0]);await button(272,1)
                for point in points[1:]: await move(point);await asyncio.sleep(.01)
                await button(272,0)
            elif kind in {'move','click','double_click','scroll'}:
                await move(action)
                if kind in {'click','double_click'}:
                    code={'left':272,'right':273,'middle':274,'wheel':274,'back':275,'forward':276}[action.get('button','left')]
                    for _ in range(2 if kind=='double_click' else 1):
                        await button(code,1);await button(code,0);await asyncio.sleep(.06)
                elif kind=='scroll':
                    for axis,value in [(0,action['scroll_y']),(1,action['scroll_x'])]:
                        if value: await self.command(f'axis {axis} {value/10}')
            elif kind=='wait': await asyncio.sleep(.25)
        finally:
            await self.command('release')
            # Allow the focused toolkit to process the completed event group.
            await asyncio.sleep(.05)
    async def close(self):
        if self.process.returncode is None:
            try:
                self.process.stdin.write(b'stop\n');await self.process.stdin.drain()
            except (BrokenPipeError,ConnectionResetError):
                pass
            try: await asyncio.wait_for(self.process.wait(),3)
            except asyncio.TimeoutError:
                self.process.kill();await self.process.wait()
