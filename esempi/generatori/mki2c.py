"""Build a synthetic 2-channel FNIRSI .wav with I2C traffic (CH1 = SCL, CH2 = SDA).

Usage: mki2c.py TEMPLATE.wav OUT.wav [HALF]
TEMPLATE is any 2-channel file saved by the scope at 2 ms/div (it provides the header).
HALF = samples per half SCL period (default 25, i.e. 10 kHz at 500 kS/s)."""
import sys, random, math
src, dst = sys.argv[1], sys.argv[2]
d = bytearray(open(src, 'rb').read())
u = lambda o, n: int.from_bytes(d[o:o + n], 'big')
tab = [u(i * 4, 4) for i in range(7)]
per, frame = u(0x12D, 4), u(0x11D, 4)          # 24000 per channel, 12000 per acquisition
rate = u(0x139, 8)                              # 500 kS/s -> 2 us per sample
assert d[0x66] == 1 and d[0xA6] == 1
# 1 V/div, zero at 1 div for both channels
for base in (0x40, 0x80):
    for off in (0x2E, 0x36):                    # u64 V/div (µV) and its copy
        d[base + off:base + off + 8] = (1_000_000).to_bytes(8, 'big')
    for off in (0x3E, 0x40):                    # zero position px and copy
        d[base + off:base + off + 2] = (27).to_bytes(2, 'big')
HALF = int(sys.argv[3]) if len(sys.argv) > 3 else 25   # 10 kHz SCL at 500 kS/s
scl, sda = [], []
def hold(c, a, n):
    scl.extend([c] * n); sda.extend([a] * n)
def byte(v, ack):
    for b in [(v >> (7 - i)) & 1 for i in range(8)] + [0 if ack else 1]:
        hold(0, sda[-1], HALF // 2); hold(0, b, HALF - HALF // 2); hold(1, b, HALF)
def start(): hold(1, 1, 20); hold(1, 0, 15); hold(0, 0, 10)
def rstart(): hold(0, 1, 10); hold(1, 1, 20); hold(1, 0, 15); hold(0, 0, 10)
def stop(): hold(0, 0, 10); hold(1, 0, 15); hold(1, 1, 20)
hold(1, 1, 500)                                 # idle 1 ms
start(); byte(0x50 << 1, True); byte(0x12, True); byte(0xA5, True)
rstart(); byte((0x50 << 1) | 1, True); byte(0x3C, True); byte(0xFF, False); stop()
hold(1, 1, 6000 - len(scl))                     # second transaction at 12 ms
start(); byte(0x27 << 1, False); stop()
hold(1, 1, frame - len(scl))
assert len(scl) == frame
random.seed(1)
def analog(levels):
    out, v, tau = [], 3.3, 2.0                  # RC edges (pull-up), tau 2 samples
    for L in levels:
        tgt = 3.3 if L else 0.0
        v += (tgt - v) * (1 - math.exp(-1 / (tau if L else 0.6)))
        out.append(v + random.gauss(0, 0.03))
    return out
counts = lambda vs: [max(0, min(12800, round((x / 1.0 + 1.0) * 1600))) for x in vs]
c_scl, c_sda = counts(analog(scl)), counts(analog(sda))
data = bytearray()
for ch in (c_scl, c_sda):
    for _ in range(per // frame):               # same traffic in every acquisition
        for c in ch: data += c.to_bytes(2, 'big')
d[tab[4]:tab[4] + tab[5]] = data
d[tab[2] + 4:tab[2] + tab[3]] = bytes(tab[3] - 4)   # blank the screen thumbnail of the template
open(dst, 'wb').write(d)
print(dst, len(d), 'per', per, 'frame', frame, 'rate', rate)
