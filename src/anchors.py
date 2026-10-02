"""Find the City Folk addresses the GameCube-pad patch needs in any revision.

Everything is written once against USA Rev 0 (RUUE01v0); the other discs share
the same compiled code at other addresses.  A function is located by matching
a window of USA instructions against the target DOL with the relocatable bits
(branch displacements, address halves, small-data offsets) masked out, and it
must match exactly once.  Data addresses are then read back from the matched
code (the lis/addi that references them), never guessed.
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
from dol import Dol

def mask(w):
    op = w >> 26
    if op in (18,):                      # b / bl: keep opcode, AA, LK
        return w & 0xFC000003
    if op == 16:                         # bc: keep everything but displacement
        return w & 0xFFFF0003
    if op in (14, 15, 24, 25, 26, 27, 28, 29):   # addi/lis/ori/oris/xori/andi
        return w & 0xFFFF0000
    if 32 <= op <= 55:                   # loads/stores: drop displacement
        return w & 0xFFFF0000
    return w

def words(d, va, n):
    b = d.read(va, n * 4)
    return list(struct.unpack('>%dI' % n, b)) if b and len(b) == n * 4 else None

class Finder:
    def __init__(self, ref, tgt):
        self.ref, self.tgt = ref, tgt
        o, a, s, _ = [x for x in tgt.secs if x[3] == 1][0]
        self.tw = struct.unpack('>%dI' % (s // 4), tgt.data[o:o + s])
        self.tbase = a
        self.tm = [mask(w) for w in self.tw]

    def _hits(self, rm, tm, tbase, n):
        hits, first = [], rm[0]
        for i in range(len(tm) - n):
            if tm[i] == first and tm[i:i + n] == rm:
                hits.append(tbase + i * 4)
        return hits

    def locate(self, ref_va, n=24, ordered=False):
        """address in the target of the code at ref_va; must match exactly once, unless
        `ordered`: identical twins are then told apart by their order in the image"""
        rw = words(self.ref, ref_va, n)
        rm = [mask(w) for w in rw]
        hits = self._hits(rm, self.tm, self.tbase, n)
        if len(hits) != 1 and ordered:
            o, a, s, _ = [x for x in self.ref.secs if x[3] == 1][0]
            rtm = [mask(w) for w in struct.unpack('>%dI' % (s // 4), self.ref.data[o:o + s])]
            rhits = self._hits(rm, rtm, a, n)
            if len(rhits) == len(hits) and ref_va in rhits:
                return hits[rhits.index(ref_va)]
        if len(hits) != 1:
            raise SystemExit('anchor %08X: %d matches' % (ref_va, len(hits)))
        return hits[0]

    def pair(self, ref_va, ref_target, n=64):
        """the target revision's value for the address that the lis + addi pair
        near ref_va loads (ref_target on USA Rev 0)"""
        t_va = self.locate(ref_va)
        rw = words(self.ref, ref_va, n)
        tw = words(self.tgt, t_va, n)

        def imm(w):
            v = w & 0xFFFF
            return v - 0x10000 if v & 0x8000 else v

        for i in range(n):
            w = rw[i]
            if w >> 26 != 15:
                continue
            reg = (w >> 21) & 31
            for j in range(i + 1, min(n, i + 16)):
                w2 = rw[j]
                if w2 >> 26 == 14 and (w2 >> 16) & 31 == reg:
                    val = ((w & 0xFFFF) << 16) + imm(w2)
                    if val & 0xFFFFFFFF == ref_target:
                        t, t2 = tw[i], tw[j]
                        assert t >> 26 == 15 and t2 >> 26 == 14
                        return (((t & 0xFFFF) << 16) + imm(t2)) & 0xFFFFFFFF
        raise SystemExit('no pair for %08X near %08X' % (ref_target, ref_va))

# (name, USA address, window of instructions to match)
FUNCS = {
    'KPADiRead':   (0x8016F500, 40),
    'WPADProbe':   (0x80129BF0, 30),
    'SIGetType':   (0x80113930, 40),
    'OSDisableInterrupts': (0x800DFE20, 6),
    'OSRestoreInterrupts': (0x800DFE60, 6),
}
# offsets inside KPADiRead (identical code in every release)
SAMPLE_SITE_OFF = 0x8016F6A4 - 0x8016F500        # lbz r0,379(r21): "any samples queued?"

# data the hooks need, read back from the matched code: (function it appears in, USA value)
USA_SI_SHADOW = 0x8030621C                     # SIPOLL as the SDK last wrote it (busy flag is 4 below)
USA_SI_TYPES = 0x80306230                      # per-channel SI device type cache
USA_WPAD_TBL = 0x80378410                      # table of pointers to the four WPAD control blocks
USA_KPAD0 = 0x803B3178                         # KPAD channel 0 state (stride 0x688)


def resolve(ref, tgt):
    f = Finder(ref, tgt)
    r = {}
    for k, (v, n) in FUNCS.items():
        r[k] = f.locate(v, n)
    r['SampleSite'] = r['KPADiRead'] + SAMPLE_SITE_OFF
    r['SiTypes'] = f.pair(0x80113930, USA_SI_TYPES)
    r['SiShadow'] = f.pair(0x80113930, USA_SI_SHADOW - 4) + 4
    r['SiBusy'] = r['SiShadow'] - 4
    r['WpadTbl'] = f.pair(0x80129BF0, USA_WPAD_TBL, 12)
    r['Kpad0'] = f.pair(0x8016F500, USA_KPAD0)
    return r


if __name__ == '__main__':
    ref = Dol(sys.argv[1])
    for p in sys.argv[2:]:
        r = resolve(ref, Dol(p))
        print(os.path.basename(p), {k: '%08X' % v for k, v in r.items()})
