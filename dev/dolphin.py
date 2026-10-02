"""Run a patched Rhythm Heaven Fever image in a private Dolphin and read it back.

A throwaway Dolphin user folder (config, saves, pipes) is built per run, so
every run starts from the same state.  Input goes in through Dolphin's Pipe
device (a named pipe per controller), and the game's KPAD state is read back
over Dolphin's GDB stub -- no screen scraping needed to know whether a press
arrived.

    from dolphin import Dolphin
    with Dolphin(image, gc=True, wiimote='classic') as d:
        d.wait_boot()
        d.gc.press('A'); print(d.kpad(0))
"""
import os
import shutil
import signal
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gdbmem import Gdb

DOLPHIN = os.environ.get('DOLPHIN', '/Applications/Dolphin.app/Contents/MacOS/Dolphin')
GDB_PORT = int(os.environ.get('RHF_GDB_PORT', '2713'))

# KPAD channel 0 struct per region (the stride between channels is 0x688)
KPAD0 = {'SOME01': 0x803B3178, 'SOMP01': 0x803B4878, 'SOMJ01': 0x803BA5B8, 'SOMK01': 0x803AEFF8}
KPAD_STRIDE = 0x688

# Classic Controller input -> pipe input (what a test sends with wii.press / wii.axis)
CLASSIC = {
    'Buttons/A': 'Button A', 'Buttons/B': 'Button B', 'Buttons/X': 'Button X', 'Buttons/Y': 'Button Y',
    'Buttons/ZL': 'Button Z', 'Buttons/ZR': 'Button START', 'Buttons/+': 'Button L', 'Buttons/-': 'Button R',
    'Triggers/L': 'Axis L +', 'Triggers/R': 'Axis R +',
    'D-Pad/Up': 'Button D_UP', 'D-Pad/Down': 'Button D_DOWN', 'D-Pad/Left': 'Button D_LEFT', 'D-Pad/Right': 'Button D_RIGHT',
    'Left Stick/Up': 'Axis MAIN Y +', 'Left Stick/Down': 'Axis MAIN Y -', 'Left Stick/Left': 'Axis MAIN X -', 'Left Stick/Right': 'Axis MAIN X +',
    'Right Stick/Up': 'Axis C Y +', 'Right Stick/Down': 'Axis C Y -', 'Right Stick/Left': 'Axis C X -', 'Right Stick/Right': 'Axis C X +',
}
# plain Wii Remote buttons, for the tests that use a remote without an extension
REMOTE = {'Buttons/A': 'Button A', 'Buttons/B': 'Button B', 'Buttons/1': 'Button X', 'Buttons/2': 'Button Y',
          'Buttons/+': 'Button START', 'Buttons/-': 'Button Z',
          'D-Pad/Up': 'Button D_UP', 'D-Pad/Down': 'Button D_DOWN', 'D-Pad/Left': 'Button D_LEFT', 'D-Pad/Right': 'Button D_RIGHT'}
# which pipe name presses which Classic button
CC_PIPE = {'A': 'A', 'B': 'B', 'X': 'X', 'Y': 'Y', 'ZL': 'Z', 'ZR': 'START', '+': 'L', '-': 'R',
           'Up': 'D_UP', 'Down': 'D_DOWN', 'Left': 'D_LEFT', 'Right': 'D_RIGHT'}

GC_NAMES = dict(A='A', B='B', X='X', Y='Y', Z='Z', Start='START', L='L', R='R',
                Up='D_UP', Down='D_DOWN', Left='D_LEFT', Right='D_RIGHT')


class Pipe:
    """One of Dolphin's named-pipe controllers: PRESS/RELEASE/SET lines."""

    def __init__(self, path):
        self.path = path
        self.f = None

    def open(self, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            try:
                self.f = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
                return
            except OSError:
                time.sleep(0.5)
        raise TimeoutError('nobody opened ' + self.path)

    def reopen(self):
        try:
            os.close(self.f)
        except OSError:
            pass
        self.open(10)

    def cmd(self, s):
        os.write(self.f, (s + '\n').encode())

    def press(self, *bs):
        """Press buttons in one write, so the emulator sees them on the same frame."""
        self.cmd('\n'.join('PRESS ' + b for b in bs))

    def release(self, *bs):
        self.cmd('\n'.join('RELEASE ' + b for b in bs))

    def axis(self, name, x, y):
        self.cmd('SET %s %.3f %.3f' % (name, x, y))

    def set1(self, name, v):
        self.cmd('SET %s %.3f' % (name, v))

    def tap(self, b, secs=0.25):
        self.press(b)
        time.sleep(secs)
        self.release(b)
        time.sleep(0.15)


def write_config(user, gc, wiimote, video_dump=False):
    for d in ('Config', 'GameSettings', 'Pipes'):
        os.makedirs(os.path.join(user, d), exist_ok=True)
    pipes = os.path.join(user, 'Pipes')
    for n in ('gc', 'wii'):
        p = os.path.join(pipes, n)
        if os.path.exists(p):
            os.unlink(p)
        os.mkfifo(p)
    open(os.path.join(user, 'Config', 'Dolphin.ini'), 'w').write(
        "[General]\nGDBPort = %d\n[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n"
        "[Core]\nMMU = True\nCPUThread = False\nCPUCore = 4\nEnableDebugging = True\nEnableCheats = True\n"
        "WiimoteContinuousScanning = False\nWiimoteControllerInterface = False\n"
        "SIDevice0 = %d\nSIDevice1 = 0\nSIDevice2 = 0\nSIDevice3 = 0\n"
        "[Analytics]\nPermissionAsked = True\nEnabled = False\n" % (GDB_PORT, 6 if gc else 0) +
        ("[Movie]\nDumpFrames = True\nDumpFramesSilent = True\nDumpFramesAsImages = True\n" if video_dump else ""))
    pad = "[GCPad1]\nDevice = Pipe/0/gc\n"
    pad += "".join("Buttons/%s = `Button %s`\n" % (b, b) for b in 'ABXYZ')
    pad += "Buttons/Start = `Button START`\n"
    pad += "".join("D-Pad/%s = `Button D_%s`\n" % (d.title(), d.upper()) for d in ('up', 'down', 'left', 'right'))
    pad += "Triggers/L = `Button L`\nTriggers/R = `Button R`\nTriggers/L-Analog = `Axis L -+`\nTriggers/R-Analog = `Axis R -+`\n"
    pad += "Main Stick/Up = `Axis MAIN Y +`\nMain Stick/Down = `Axis MAIN Y -`\nMain Stick/Left = `Axis MAIN X -`\nMain Stick/Right = `Axis MAIN X +`\n"
    pad += "C-Stick/Up = `Axis C Y +`\nC-Stick/Down = `Axis C Y -`\nC-Stick/Left = `Axis C X -`\nC-Stick/Right = `Axis C X +`\n"
    open(os.path.join(user, 'Config', 'GCPadNew.ini'), 'w').write(pad)

    if wiimote:
        # The pipe device only has GameCube-shaped inputs, so a Classic Controller is wired onto them:
        # see CLASSIC below for which pipe name drives which Classic input.
        w = "[Wiimote1]\nSource = 1\nDevice = Pipe/0/wii\nExtension = %s\n" % {'classic': 'Classic', 'nunchuk': 'Nunchuk', 'none': 'None'}[wiimote]
        if wiimote in ('none', 'nunchuk'):
            for k, v in REMOTE.items():
                w += "%s = `%s`\n" % (k, v)
        if wiimote == 'classic':
            for k, v in CLASSIC.items():
                w += "Classic/%s = `%s`\n" % (k, v)
    else:
        w = "[Wiimote1]\nSource = 0\n"
    open(os.path.join(user, 'Config', 'WiimoteNew.ini'), 'w').write(w)


class Dolphin:
    def __init__(self, image, user=None, gc=False, wiimote=None, video='Null', region='SOME01', video_dump=False):
        self.image = os.path.abspath(image)
        self.user = os.path.abspath(user or os.environ.get('DOLPHIN_USER') or os.path.join(HERE, '..', '.dolphin_user'))
        self.gc_on, self.wii_on, self.video, self.region = gc, wiimote, video, region
        self.video_dump = video_dump
        self.proc = None
        self.g = None
        self.gc = Pipe(os.path.join(self.user, 'Pipes', 'gc'))
        self.wii = Pipe(os.path.join(self.user, 'Pipes', 'wii'))

    def __enter__(self):
        shutil.rmtree(self.user, ignore_errors=True)
        write_config(self.user, self.gc_on, self.wii_on, self.video_dump)
        self.proc = subprocess.Popen([DOLPHIN, '-b', '-u', self.user, '-e', self.image, '-v', self.video],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            try:
                self.g = Gdb(port=GDB_PORT, timeout=30)
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('Dolphin GDB stub never came up')
        self.g.drain(1.0)           # the stub announces its initial stop
        self.g.cont()
        if self.gc_on:
            self.gc.open()
        if self.wii_on:
            self.wii.open()
        return self

    def __exit__(self, *a):
        try:
            if self.g:
                self.g.close()
        finally:
            if self.proc:
                self.proc.send_signal(signal.SIGTERM)
                try:
                    self.proc.wait(10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()

    # -- memory -----------------------------------------------------------
    # Each stop of the emulated CPU is about a second (the stub needs it to settle).  That is fine
    # for a game driven by a GameCube pad; with a real Wii Remote involved the game's remote
    # library gives up during a long stop, so read sparingly there.
    def peek(self, addr, n):
        self.g.interrupt()
        try:
            return self.g.read_mem(addr, n)
        finally:
            self.g.cont()

    def poke(self, addr, data):
        self.g.interrupt()
        try:
            self.g.cmd('M%x,%x:%s' % (addr, len(data), data.hex()))
        finally:
            self.g.cont()

    def kpad_base(self, chan=0):
        return KPAD0[self.region] + chan * KPAD_STRIDE

    def kpad(self, chan=0):
        b = self.peek(self.kpad_base(chan), 0x188)
        u32 = lambda o: struct.unpack('>I', b[o:o + 4])[0]
        f32 = lambda o: struct.unpack('>f', b[o:o + 4])[0]
        return dict(hold=u32(0), trig=u32(4), rel=u32(8), dev=b[0x5C], err=b[0x5D], dpd=b[0x5E],
                    cl_hold=u32(0x60), ls=(f32(0x6C), f32(0x70)), rs=(f32(0x74), f32(0x78)),
                    ptr=(f32(0x20), f32(0x24)), ring_idx=b[0x17A], ring_cnt=b[0x17B])

    def wait_boot(self, secs=25):
        time.sleep(secs)
