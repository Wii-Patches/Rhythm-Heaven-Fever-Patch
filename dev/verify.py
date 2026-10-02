#!/usr/bin/env python3
"""Region-by-region check of the GameCube controller patch in Dolphin.

For each release: patch a copy of the disc image (Classic Controller + GameCube pad, with the
pad's response fed through memory so the check is deterministic), boot it with no Wii Remote,
and assert what the game's own KPAD state holds for every pad input.

    RHF_DISCS=/dir/with/wbfs  python3 dev/verify.py [SOME01 SOMP01 ...]

The discs are looked up by disc id in RHF_DISCS (any *.wbfs / *.iso).  Needs wit and Dolphin.
"""
import glob
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from dolphin import Dolphin

STATE = 0x80005F00
BASE_H, BASE_L = 0x00808080, 0x80800000

# pad input -> expected KPAD hold word (Wii Remote bits) the game sees
H = dict(A=0x01000000, B=0x02000000, X=0x04000000, Y=0x08000000, Start=0x10000000, Z=0x00100000,
         L=0x00400000, R=0x00200000, Up=0x00080000, Down=0x00040000, Right=0x00020000, Left=0x00010000)
EXPECT = dict(A=0x0800, B=0x0400, X=0x0800, Y=0x0200, Start=0x0010, Z=0x8000, L=0x0800, R=0x0400,
              Up=0x0008, Down=0x0004, Right=0x0002, Left=0x0001)


def feed(d, h, l):
    d.poke(STATE + 0x20, struct.pack('>II', h, l))


def read_kpad(d):
    return d.kpad()


def stick(x, y):
    return (BASE_H & ~0xFFFF) | (int(128 + 127 * x) << 8) | int(128 + 127 * y)


def find_disc(discs, rid):
    for p in sorted(glob.glob(os.path.join(discs, '*.wbfs')) + glob.glob(os.path.join(discs, '*.iso'))):
        r = subprocess.run(['wit', 'ID6', p], capture_output=True, text=True).stdout.strip()
        if r == rid:
            return p
    raise SystemExit('no disc with id %s in %s' % (rid, discs))


def build_all(regions, discs, work):
    """Patch a copy of each disc with data built from the retail DOLs, the pad fed through memory."""
    dols = os.path.join(work, 'dols')
    os.makedirs(dols)
    srcs = {}
    for r in ['SOME01', 'SOMP01', 'SOMJ01', 'SOMK01']:
        srcs[r] = find_disc(discs, r)
        out = os.path.join(work, 'x_' + r)
        subprocess.check_call(['wit', 'extract', srcs[r], '--dest', out, '--psel', 'data', '--files', '+/sys/main.dol',
                               '--flat', '-q'])
        shutil.move(os.path.join(out, 'main.dol'), os.path.join(dols, r + '.dol'))
    pre = os.path.join(work, 'prebuilt')
    env = dict(os.environ, RHF_DEBUG_FEED='1', RHF_DOLS=dols, RHF_PREBUILT=pre)
    subprocess.check_call([sys.executable, os.path.join(ROOT, 'tools', 'gen_prebuilt.py')], env=env)
    imgs = {}
    for r in regions:
        imgs[r] = os.path.join(work, r + '.wbfs')
        shutil.copyfile(srcs[r], imgs[r])
        subprocess.check_call([sys.executable, os.path.join(ROOT, 'tools', 'patch_disc.py'), imgs[r], '--cc', '--gc'], env=env)
    return imgs


def main():
    regions = sys.argv[1:] or ['SOME01', 'SOMP01', 'SOMJ01', 'SOMK01']
    discs = os.environ.get('RHF_DISCS') or sys.exit('set RHF_DISCS=<dir with the four .wbfs>')
    user = os.environ.get('DOLPHIN_USER') or os.path.join(tempfile.gettempdir(), 'rhf_dolphin_user')
    failed = []
    with tempfile.TemporaryDirectory(prefix='rhf_verify_') as work:
        imgs = build_all(regions, discs, work)
        for region in regions:
            img = imgs[region]
            print('== %s' % region, flush=True)
            with Dolphin(img, user=user, gc=True, region=region) as d:
                time.sleep(float(os.environ.get('BOOT', 40)))
                ok = True
                for name, h in H.items():
                    for attempt in range(3):         # a loaded machine can skip a beat; a real bug never passes
                        feed(d, BASE_H | h, BASE_L); time.sleep(0.8 + attempt)
                        k = read_kpad(d)
                        good = k['hold'] == EXPECT[name] and k['dev'] == 2
                        if good:
                            break
                    ok &= good
                    print('  %-6s hold=%04X (want %04X) dev=%d %s' % (name, k['hold'], EXPECT[name], k['dev'], 'ok' if good else 'FAIL'), flush=True)
                    feed(d, BASE_H, BASE_L); time.sleep(0.3)
                feed(d, stick(1.0, 0.0), BASE_L); time.sleep(0.8); k = read_kpad(d)
                good = k['hold'] == 0x0002 and abs(k['ls'][0] - 1.0) < 0.01
                ok &= good
                print('  stick right: hold=%04X ls=%s %s' % (k['hold'], k['ls'], 'ok' if good else 'FAIL'))
                feed(d, BASE_H, 0x80FF0000); time.sleep(0.8); k = read_kpad(d)
                good = k['rs'][1] > 0.9
                ok &= good
                print('  C-stick up : rs=%s dpd=%d %s' % (k['rs'], k['dpd'], 'ok' if good else 'FAIL'))
                if not ok:
                    failed.append(region)
    print('FAILED: ' + ', '.join(failed) if failed else 'ok: all regions pass')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
