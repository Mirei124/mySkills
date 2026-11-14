"""Verify Unicode keymap semantics without accessing the desktop."""
import ctypes as c
import unittest

class KeymapTests(unittest.TestCase):
    def test_unicode_ac01_symbol(self):
        lib=c.CDLL('libxkbcommon.so.0')
        lib.xkb_context_new.argtypes=[c.c_int];lib.xkb_context_new.restype=c.c_void_p
        lib.xkb_keymap_new_from_string.argtypes=[c.c_void_p,c.c_char_p,c.c_int,c.c_int];lib.xkb_keymap_new_from_string.restype=c.c_void_p
        lib.xkb_keymap_key_get_syms_by_level.argtypes=[c.c_void_p,c.c_uint,c.c_uint,c.c_uint,c.POINTER(c.POINTER(c.c_uint))]
        lib.xkb_keymap_key_get_syms_by_level.restype=c.c_int
        lib.xkb_keymap_unref.argtypes=[c.c_void_p];lib.xkb_context_unref.argtypes=[c.c_void_p]
        context=lib.xkb_context_new(0)
        self.assertTrue(context)
        try:
            source=b'xkb_keymap { xkb_keycodes { include "evdev+aliases(qwerty)" }; xkb_types { include "complete" }; xkb_compatibility { include "complete" }; xkb_symbols { include "pc+us" key <AC01> { [ U4F60 ] }; }; };'
            keymap=lib.xkb_keymap_new_from_string(context,source,1,0)
            self.assertTrue(keymap)
            try:
                syms=c.POINTER(c.c_uint)()
                count=lib.xkb_keymap_key_get_syms_by_level(keymap,38,0,0,c.byref(syms))
                self.assertEqual(count,1)
                self.assertEqual(syms[0],0x1004f60)
            finally: lib.xkb_keymap_unref(keymap)
        finally: lib.xkb_context_unref(context)
