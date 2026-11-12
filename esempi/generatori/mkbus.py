"""Synthetic UART (2 channels) and 1-Wire (1 channel) files in the FNIRSI .wav format.

Usage: mkbus.py uart TEMPLATE_2CH.wav OUT.wav   (template: 2 channels, 2 ms/div)
       mkbus.py ow   TEMPLATE_1CH.wav OUT.wav   (template: 1 channel, 1 ms/div)
The template only provides the header; V/div, zero and data are replaced."""
import sys, random, math
kind, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
d = bytearray(open(src, 'rb').read())
u = lambda o, n: int.from_bytes(d[o:o + n], 'big')
tab = [u(i * 4, 4) for i in range(7)]
per, frame, rate = u(0x12D, 4), u(0x11D, 4), u(0x139, 8)
dt = 1 / rate
on = [d[0x66] == 1, d[0xA6] == 1]
for base in (0x40, 0x80):
    for off in (0x2E, 0x36): d[base + off:base + off + 8] = (1_000_000).to_bytes(8, 'big')
    for off in (0x3E, 0x40): d[base + off:base + off + 2] = (27).to_bytes(2, 'big')
random.seed(2)
def analog(levels, tau_up=1.5, tau_dn=0.5):
    out, v = [], 3.3
    for L in levels:
        tgt = 3.3 if L else 0.0
        v += (tgt - v) * (1 - math.exp(-1 / (tau_up if L else tau_dn)))
        out.append(v + random.gauss(0, 0.03))
    return out
counts = lambda vs: [max(0, min(12800, round((x + 1.0) * 1600))) for x in vs]
def at(t): return int(round(t / dt))
if kind == 'uart':
    baud = 9600; nb = 1 / baud
    def line(chunks):
        lv = [1] * frame
        for t0, data, bad_stop in chunks:
            t = t0
            for j, ch in enumerate(data):
                bits = [0] + [(ch >> b) & 1 for b in range(8)] + [0 if (bad_stop and j == len(data) - 1) else 1]
                for b in bits:
                    for i in range(at(t), min(frame, at(t + nb))): lv[i] = b
                    t += nb
                for i in range(at(t), min(frame, at(t + nb))): lv[i] = 1   # restore idle after a bad stop
        return lv
    tx = line([(1e-3, b"Hello\r\n", False), (12e-3, b"AT", False)])
    rx = line([(9e-3, b"OK\r\n", False), (17e-3, b"\x55", True)])
    chans = [counts(analog(tx)), counts(analog(rx))]
elif kind == 'ow':
    lv = [1] * frame
    t = [0.5e-3]
    def low(dur, rec):
        for i in range(at(t[0]), at(t[0] + dur)): lv[i] = 0
        t[0] += dur + rec
    def reset(presence=True):
        low(500e-6, 0)
        if presence:
            t[0] += 30e-6; low(120e-6, 350e-6)
        else:
            t[0] += 500e-6
    def wbyte(v):
        for b in range(8):
            if (v >> b) & 1: low(6e-6, 64e-6)
            else: low(65e-6, 5e-6)
    def crc8(bs):
        c = 0
        for x in bs:
            for _ in range(8):
                mix = (c ^ x) & 1; c >>= 1
                if mix: c ^= 0x8C
                x >>= 1
        return c
    raw = int(25.0625 * 16)
    sp = [raw & 255, raw >> 8, 0x4B, 0x46, 0x7F, 0xFF, 0x0F, 0x10]
    sp.append(crc8(sp))
    reset(); wbyte(0xCC); wbyte(0xBE)
    for v in sp: wbyte(v)          # read slots look the same on the wire
    t[0] += 300e-6
    reset(presence=False)
    chans = [counts(analog(lv, 3.0, 0.4))]
    print('scratchpad', ' '.join(f'{x:02X}' for x in sp), 'end at', round(t[0] * 1e3, 2), 'ms')
data = bytearray()
for ch in chans:
    for _ in range(per // frame):
        for c in ch: data += c.to_bytes(2, 'big')
assert len(data) == tab[5], (len(data), tab[5])
d[tab[4]:tab[4] + tab[5]] = data
d[tab[2] + 4:tab[2] + tab[3]] = bytes(tab[3] - 4)   # blank the screen thumbnail of the template
open(dst, 'wb').write(d)
print(dst, 'rate', rate, 'frame', frame, 'ch', on)
