import os
import sys, time, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dolphin import Dolphin
with Dolphin(sys.argv[1], user=os.environ.get('DOLPHIN_USER', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.dolphin_user')), wiimote='classic') as d:
    d.wait_boot(25)
    def dump(tag):
        b = d.peek(d.kpad_base(0), 0x5B0)
        idx, cnt = b[0x17A], b[0x17B]
        print(tag, 'idx', idx, 'cnt', cnt, 'ext/ring0', struct.unpack('>I', b[0x5A0:0x5A4])[0], struct.unpack('>I', b[0x5A4:0x5A8])[0])
        for slot in range(16):
            e = b[0x180 + slot * 0x42: 0x180 + (slot + 1) * 0x42]
            if any(e): print('  slot', slot, e.hex(' '))
    dump('idle')
    d.wii.press('A'); d.wii.axis('MAIN', 1.0, 0.75); d.wii.axis('C', 0.0, 0.5); d.wii.set1('R', 1.0); time.sleep(0.6)
    dump('held A, LS right/up, RS left, R trig')
