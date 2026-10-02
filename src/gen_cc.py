"""Build the Classic Controller feature: Vague Rant's Gecko codes, as ops.

The codes in src/cc/<ID>.txt are his (see README credits); this only parses
them into Hook ops so the same data can become a patched DOL, a Gecko list
or a Riivolution patch.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
from layout import CC_BASE, CC_END
from ops import Feature, Hook


def parse(text):
    lines = [l.split()[:2] for l in text.splitlines() if l.strip() and not l.lstrip().startswith(('*', '$', '#'))]
    i, out = 0, []
    while i < len(lines):
        a, b = lines[i]
        try:
            ok = len(a) == 8 and len(b) == 8 and int(a, 16) >= 0 and int(b, 16) >= 0
        except ValueError:
            ok = False
        if not ok:                            # the code's title line
            i += 1
            continue
        kind, addr = int(a[:2], 16), 0x80000000 | (int(a[2:], 16) & 0x01FFFFFF)
        if kind == 0x04:
            out.append(('04', addr, [int(b, 16)]))
            i += 1
        elif kind == 0xC2:
            n = int(b, 16)
            ws = [int(x, 16) for ln in lines[i + 1:i + 1 + n] for x in ln]
            out.append(('C2', addr, ws))
            i += 1 + n
        else:
            raise ValueError('unsupported code line: %s %s' % (a, b))
    return out


NOTES = ['calc_dpd_variable: right stick -> IR pointer (HOME Menu)',
         'read_kpad_stick: left stick -> D-pad',
         'read_kpad_button: Classic Controller buttons -> Wii Remote bits']


def build(region, dol):
    text = open(os.path.join(HERE, 'cc', region + '.txt')).read()
    ops, cur = [], CC_BASE
    notes = list(NOTES)
    for kind, addr, body in parse(text):
        if kind != 'C2':
            raise SystemExit('unexpected %s code in %s' % (kind, region))
        orig = struct.unpack('>I', dol.read(addr, 4))[0]
        assert body[-1] == 0
        ops.append(Hook(addr, orig, body, cur, note=notes.pop(0)))
        cur += (len(body) * 4 + 15) & ~15
    if cur > CC_END:
        raise SystemExit('cc code overflows its window')
    return Feature('cc', 'Classic Controller', region, ops)
