"""Boot an image with frame dumping and press things on a schedule; frames land in <out>/."""
import glob, os, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dolphin import Dolphin
img, out = sys.argv[1], sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else 'gc'
steps = sys.argv[4].split(',') if len(sys.argv) > 4 else []
os.makedirs(out, exist_ok=True)
user = os.environ.get('DOLPHIN_USER', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.dolphin_user'))
with Dolphin(img, user=user, gc=(mode == 'gc'), wiimote=None if mode == 'gc' else mode, video='Metal', video_dump=True) as d:
    pad = d.gc if mode == 'gc' else d.wii
    t0 = time.time()
    n = 0
    def shot(tag):
        global n
        time.sleep(1.0)
        fr = sorted(glob.glob(os.path.join(user, 'Dump', 'Frames', '**', '*.png'), recursive=True), key=os.path.getmtime)
        if fr:
            shutil.copy(fr[-2] if len(fr) > 1 else fr[-1], os.path.join(out, '%02d_%s.png' % (n, tag))); n += 1
    time.sleep(float(os.environ.get('BOOT', 30)))
    shot('boot')
    for s in steps:
        # "A:1.0" press A, hold 1.0s ; "w:5" wait ; "s:tag" screenshot
        k, v = s.split(':')
        if k == 'w': time.sleep(float(v))
        elif k == 's': shot(v)
        else:
            ks = k.split('+')
            pad.press(*ks)
            time.sleep(float(v) / 2)
            kk = d.kpad() if not os.environ.get('NOKPAD') else dict(hold=0, cl_hold=0, dev=0, ring_cnt=0); print('  %s held: hold=%08X cl=%08X dev=%d cnt=%d' % (k, kk['hold'], kk['cl_hold'], kk['dev'], kk['ring_cnt']), flush=True)
            time.sleep(float(v) / 2)
            pad.release(*ks)
            time.sleep(0.3)
