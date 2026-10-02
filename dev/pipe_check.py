import os
import sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dolphin import Dolphin
img = sys.argv[1]
with Dolphin(img, user=os.environ.get('DOLPHIN_USER', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.dolphin_user')), gc=True, wiimote=None) as d:
    d.wait_boot(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    print('idle', d.kpad())
    for b in ('A', 'B', 'X', 'Y', 'Z', 'Start', 'L', 'R', 'Up', 'Down', 'Left', 'Right'):
        n = {'Start': 'START', 'Up': 'D_UP', 'Down': 'D_DOWN', 'Left': 'D_LEFT', 'Right': 'D_RIGHT'}.get(b, b)
        d.gc.press(n); time.sleep(0.7)
        k = d.kpad(); print('%-5s hold=%08X cl=%08X dev=%d cnt=%d' % (b, k['hold'], k['cl_hold'], k['dev'], k['ring_cnt']), flush=True)
        d.gc.release(n); time.sleep(0.4)
    d.gc.axis('MAIN', 1.0, 0.5); time.sleep(0.7); k = d.kpad(); print('stick right hold=%08X ls=%s' % (k['hold'], k['ls']))
    d.gc.axis('MAIN', 0.5, 0.5); d.gc.axis('C', 1.0, 0.5); time.sleep(0.7); k = d.kpad(); print('cstick right rs=%s ptr=%s dpd=%d' % (k['rs'], k['ptr'], k['dpd']))
