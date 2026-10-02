"""Drive the DEBUG_FEED build: pad responses are poked into STATE+0x20 over GDB.
usage: play_feed.py image outdir boot  step...    step = name:secs (A B X Y Z S L R U D LT RT, N) or s:tag"""
import glob, os, shutil, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dolphin import Dolphin
STATE = 0x80005F00
BTN = dict(A=0x01000000, B=0x02000000, X=0x04000000, Y=0x08000000, S=0x10000000, Z=0x00100000, L=0x00400000,
           R=0x00200000, U=0x00080000, D=0x00040000, LT=0x00010000, RT=0x00020000)
def state(name):
    h, l = 0x00808080, 0x80800000
    for part in name.split('+'):
        if part in BTN: h |= BTN[part]
        elif part.startswith('stk='):
            x, y = [float(v) for v in part[4:].split(',')]; h = (h & ~0xFFFF) | (int(128 + 127 * x) << 8) | int(128 + 127 * y)
        elif part.startswith('cst='):
            x, y = [float(v) for v in part[4:].split(',')]; l = (int(128 + 127 * x) << 24) | (int(128 + 127 * y) << 16)
    return h, l
img, out, boot = sys.argv[1], sys.argv[2], float(sys.argv[3])
os.makedirs(out, exist_ok=True)
user = os.environ.get('DOLPHIN_USER', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.dolphin_user'))
with Dolphin(img, user=user, gc=True, video='Metal', video_dump=True) as d:
    n = 0
    def shot(tag):
        global n
        time.sleep(1.0)
        fr = sorted(glob.glob(os.path.join(user, 'Dump', 'Frames', '**', '*.png'), recursive=True), key=os.path.getmtime)
        if len(fr) > 1:
            dst = os.path.join(out, '%02d_%s.png' % (n, tag)); shutil.copy(fr[-2], dst); n += 1
            os.system('sips -Z 420 -s format jpeg "%s" --out "%s" >/dev/null 2>&1' % (dst, dst[:-4] + '.jpg'))
    def feed(name):
        h, l = state(name); d.poke(STATE + 0x20, struct.pack('>II', h, l))
    time.sleep(boot)
    feed('N')
    for s in sys.argv[4:]:
        k, v = s.split(':')
        if k == 's': shot(v)
        elif k == 'w': time.sleep(float(v))
        else:
            feed(k); time.sleep(float(v)); feed('N'); time.sleep(0.3)
