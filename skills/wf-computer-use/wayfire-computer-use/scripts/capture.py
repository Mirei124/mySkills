"""Persistent portal PipeWire capture with fresh-frame observations."""
import asyncio
import os
import time
from pathlib import Path
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

class CaptureError(RuntimeError):
    pass

class Capture:
    def __init__(self, portal, node):
        self.portal = portal
        self.fd = os.dup(portal.remote_fd)
        self.pipeline = Gst.parse_launch('pipewiresrc name=source ! videoconvert ! video/x-raw,format=RGB ! appsink name=sink max-buffers=1 drop=true sync=false')
        source = self.pipeline.get_by_name('source')
        source.set_property('fd', self.fd)
        source.set_property('path', str(node))
        source.set_property('do-timestamp', True)
        self.sink = self.pipeline.get_by_name('sink')
        self.pipeline.set_state(Gst.State.PLAYING)

    def _frame(self, after, timeout):
        deadline = time.monotonic() + timeout
        # Discard queued samples: the returned buffer must arrive after this call.
        while self.sink.emit('try-pull-sample', 0) is not None:
            if time.monotonic() >= deadline:
                raise CaptureError('CAPTURE_TIMEOUT')
        while time.monotonic() < deadline:
            message = self.pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if message:
                raise CaptureError('CAPTURE_ENDED')
            sample = self.sink.emit('try-pull-sample', 100 * Gst.MSECOND)
            if sample is None:
                continue
            buffer = sample.get_buffer()
            clock = self.pipeline.get_clock()
            if not clock or buffer.pts == Gst.CLOCK_TIME_NONE:
                raise CaptureError('FRAME_TIMESTAMP_UNAVAILABLE')
            age = (clock.get_time() - self.pipeline.get_base_time() - buffer.pts) / Gst.SECOND
            if time.monotonic() - max(age, 0) < after:
                continue
            caps = sample.get_caps().get_structure(0)
            width, height = caps.get_value('width'), caps.get_value('height')
            ok, data = buffer.map(Gst.MapFlags.READ)
            if not ok:
                raise CaptureError('FRAME_MAP_FAILED')
            try:
                # GStreamer RGB rows are aligned to four bytes.
                stride = (width * 3 + 3) & ~3
                pixels = b''.join(bytes(data.data[y*stride:y*stride+width*3]) for y in range(height))
            finally:
                buffer.unmap(data)
            return width, height, pixels
        raise CaptureError('CAPTURE_TIMEOUT')

    async def observe(self, path, after=None, timeout=8):
        width, height, pixels = await asyncio.to_thread(self._frame, after or time.monotonic(), timeout)
        import struct
        import zlib
        def chunk(kind, data):
            return struct.pack('!I',len(data)) + kind + data + struct.pack('!I',zlib.crc32(kind+data))
        raw = b''.join(b'\0'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',struct.pack('!2I5B',width,height,8,2,0,0,0)) + chunk(b'IDAT',zlib.compress(raw)) + chunk(b'IEND',b'')
        descriptor = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as target:
            target.write(png)
        return {'screenshot_path':str(Path(path).resolve()),'width':width,'height':height}

    def close(self):
        self.pipeline.set_state(Gst.State.NULL)
        os.close(self.fd)
