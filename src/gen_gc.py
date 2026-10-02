"""Build the GameCube controller feature for one release from src/gcpad/.

Three hooks (poll, sample, probe), each a small C routine behind an
assembly entry stub.  Addresses are found per release by src/anchors.py,
never hard-coded, and the C is compiled once per hook per release with
them as -D macros.  Needs devkitPPC; end users get the prebuilt JSON.
"""
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
sys.path.insert(0, HERE)
import anchors
from dol import Dol
from layout import GC_BASE, GC_END, STATE, STATE_END
from ops import Feature, Hook

DEVKIT = os.environ.get('DEVKITPPC', '/opt/devkitpro/devkitPPC')
GCC = DEVKIT + '/bin/powerpc-eabi-'
USA_DOL = None                                # set by gen_prebuilt: the USA main.dol is the reference

# the instruction each hook displaces (identical code in every release)
DISPLACED = {'POLL': 0x9421FDC0,              # stwu r1,-576(r1)      KPADiRead entry
             'SAMPLE': 0x8815017B,            # lbz r0,0x17b(r21)     KPADiRead, samples-queued test
             'PROBE': 0x9421FFF0}             # stwu r1,-16(r1)       WPADProbe entry


def compile_hook(name, defs, debug_feed=False):
    src = os.path.join(HERE, 'gcpad')
    tmp = tempfile.mkdtemp(prefix='gcpad')
    d = ['-D%s=%s' % kv for kv in defs.items()] + ['-DHOOK_' + name]
    if debug_feed:
        d.append('-DDEBUG_FEED')
    cflags = ['-O2', '-fno-unroll-loops', '-mbig-endian', '-msoft-float', '-msdata=none', '-ffreestanding',
              '-fno-pic', '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-nostdlib', '-Wall',
              '-Werror']
    subprocess.check_call([GCC + 'gcc'] + cflags + d + ['-c', src + '/gcpad.c', '-o', tmp + '/g.o'])
    subprocess.check_call([GCC + 'gcc', '-mbig-endian', '-c', '-x', 'assembler-with-cpp'] + d +
                          [src + '/hooks.S', '-o', tmp + '/h.o'])
    subprocess.check_call([GCC + 'ld', '-T', src + '/link.ld', '-o', tmp + '/b.elf', tmp + '/h.o', tmp + '/g.o'])
    subprocess.check_call([GCC + 'objcopy', '-O', 'binary', tmp + '/b.elf', tmp + '/b.bin'])
    b = open(tmp + '/b.bin', 'rb').read()
    return list(struct.unpack('>%dI' % (len(b) // 4), b))


def build(region, dol, debug_feed=bool(os.environ.get('RHF_DEBUG_FEED'))):
    ref = USA_DOL if region != 'SOME01' else dol
    a = anchors.resolve(ref, dol)
    if dol.read(STATE, STATE_END - STATE) != bytes(STATE_END - STATE):
        raise SystemExit('%s: the state area at 0x%08X is not zero padding' % (region, STATE))
    defs = {
        'STATE': '0x%08Xu' % STATE,
        'SI_TYPES': '0x%08Xu' % a['SiTypes'],
        'SI_BUSY': '0x%08Xu' % a['SiBusy'],
        'SI_SHADOW': '0x%08Xu' % a['SiShadow'],
        'FN_SIGETTYPE': '0x%08Xu' % a['SIGetType'],
        'FN_OSDISABLE': '0x%08Xu' % a['OSDisableInterrupts'],
        'FN_OSRESTORE': '0x%08Xu' % a['OSRestoreInterrupts'],
        'WPAD_TBL': '0x%08Xu' % a['WpadTbl'],
    }
    sites = [('POLL', a['KPADiRead']), ('SAMPLE', a['SampleSite']), ('PROBE', a['WPADProbe'])]
    notes = {'POLL': 'KPADiRead: drive the SI auto-poll for port 1, recover from unplugging',
             'SAMPLE': 'KPADiRead: write the pad into KPAD\'s sample ring as a Classic Controller',
             'PROBE': 'WPADProbe: report a Classic Controller on channel 0 while a pad is plugged in'}
    ops, cur = [], GC_BASE
    for name, site in sites:
        orig = struct.unpack('>I', dol.read(site, 4))[0]
        if orig != DISPLACED[name]:
            raise SystemExit('%s: %s site 0x%08X holds 0x%08X, expected 0x%08X' % (region, name, site, orig, DISPLACED[name]))
        w = compile_hook(name, defs, debug_feed)
        assert w[-1] == 0x60000000
        w[-1] = 0                                 # the slot the installer turns into the branch back
        ops.append(Hook(site, orig, w, cur, note=notes[name]))
        cur += (len(w) * 4 + 15) & ~15
    if cur > GC_END:
        raise SystemExit('gc code overflows its window: 0x%X > 0x%X' % (cur, GC_END))
    return Feature('gc', 'GameCube controller', region, ops)
