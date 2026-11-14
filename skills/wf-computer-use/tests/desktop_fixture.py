"""Dedicated GTK input fixture; writes only its own test state."""
import argparse
import json
import os
import secrets
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--state',type=Path,required=True)
args=parser.parse_args()
token=secrets.token_hex(8)
window=Gtk.Window(title='Wayfire Computer Use Test '+token)
window.set_default_size(700,400)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
box.set_border_width(24)
box.pack_start(Gtk.Label(label='Dedicated input test window'),False,False,0)
entry=Gtk.Entry()
entry.set_placeholder_text('Input test target')
box.pack_start(entry,False,False,0)
events=[]
status=Gtk.Label(label='No input received')
box.pack_start(status,False,False,0)
def changed(widget):
    text=widget.get_text()
    save_state()
    status.set_text('Test state updated')
def save_state(*unused):
    state={'pid':os.getpid(),'title':window.get_title(),'token':token,'active':window.is_active(),'entry_focused':entry.has_focus(),'text':entry.get_text(),'events':events[-100:]}
    temporary=args.state.with_suffix('.tmp')
    temporary.write_text(json.dumps(state,ensure_ascii=False))
    temporary.replace(args.state)
    return False
def pointer_event(widget,event):
    events.append({'type':event.type.value_nick,'x':round(event.x,1),'y':round(event.y,1),'button':getattr(event,'button',None)})
    save_state()
    return False
entry.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
for name in ('button-press-event','button-release-event','motion-notify-event','scroll-event'):
    entry.connect(name,pointer_event)
entry.connect('changed',changed)
entry.connect('notify::has-focus',save_state)
window.connect('notify::is-active',save_state)
window.add(box)
window.connect('destroy',Gtk.main_quit)
window.show_all()
save_state()
Gtk.main()
