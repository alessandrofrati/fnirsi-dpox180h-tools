# FNIRSI DPOX180H file format

Specification of the files saved by the scope with firmware V40, as used by `fnirsi.py` and the viewer. Entries marked "inferred" come from comparing files saved with different settings.

## Waveforms (`/Waveform/N.wav`)

The file is not an audio WAV. **Every field is big-endian**, samples included.

### Leading table (7 × u32)

| Offset | Field |
|---|---|
| 0x00 | start of the settings (always 0x32) |
| 0x04 | length of the settings |
| 0x08 | start of the thumbnail |
| 0x0C | length of the thumbnail |
| 0x10 | start of the data |
| 0x14 | length of the data |
| 0x18 | total file length |

### Thumbnail
`u16 width`, `u16 height` (usually 102×54), then width × height RGB565 pixels, top row first.

### Data
- **Samples:** they are **u16** and start **exactly** at the start of the data block (the value at 0x10), with no bytes to skip. 1600 counts per vertical division, 8 divisions on screen.
- **Channel order:** first all the CH1 samples (if byte 0x66 is 1), then all the CH2 samples (if byte 0xA6 is 1).
- **Samples per channel:** u32 at **0x12D**.
- **Samples in one acquisition:** u32 at **0x11D**, equal to sample rate × time/div × 12 divisions, that is one screen.
- **Acquisitions:** each channel holds 0x12D / 0x11D acquisitions of the same window, one after the other. There are 1 or 2 at slow time bases, 3 at 2 µs/div, 10 at 50–100 ns/div.
  - **The first is the one the screen showed:** it matches the thumbnail.
  - The others are separate acquisitions, not a continuation of the first.
- **Empty samples:** each acquisition may start with a few zero samples.
- **Conversion to volts:** V = (counts / 1600 − zero) × V/div, with the zero in divisions from the bottom (see below).

### Settings (from offset 0x32)

| Offset | Type | Meaning |
|---|---|---|
| 0x62 + k·0x40 | channel block (k = 0 CH1, 1 CH2) | |
| +0x04 (0x66 / 0xA6) | u8 | channel on |
| +0x07 (0x69 / 0xA9) | u8 | V/div range index (9 = 10 mV, 10 = 5 mV), inferred |
| +0x0C (0x6E / 0xAE) | u64 | V/div in µV |
| +0x14 (0x76 / 0xB6) | u64 | copy of V/div |
| +0x1C (0x7E / 0xBE) | u16 | zero position in pixels from the bottom, 25 px per division, offset by 2: zero in divisions = (px − 2) / 25 (copy at +0x1E) |
| 0x112 / 0x11D / 0x121 | u32 | record lengths (0x11D = samples in one acquisition) |
| 0x12D | u32 | samples per channel in the file |
| 0x139 | u64 | sample rate in Hz |
| 0x1D4 | u8 | time base index (28 = 2 ms, 26 = 500 µs), inferred |
| 0x1D5 | u64 | time/div in picoseconds |
| 0x1E9 | u16 | N1 = number of entries in the table at 0x2B8 |
| 0x2B8 | N1 × (3 × u32) | variable table: moves every later field forward by 12·(N1−1) bytes |
| end | N2 × u16 | N2 = 24 in the files examined |

Settings length = 0x353 + 12·N1 + 2·N2. In the files examined: 0x38F, 0x39B and 0x3A7 for N1 = 1, 2 and 3.

An easy mistake: reading the samples little-endian with an offset of a few bytes. The trace looks almost right, but it is shifted and has occasional jumps of ±256 counts.

## Screenshots (`/Screenshots/N.bmp`)
- **Format:** standard 320×240 BMP, 16-bit, BI_BITFIELDS RGB565 (masks F800/07E0/001F).
- **Pixels:** start at **0x2710** (10000).
- **Thumbnail:** between 0x46 and 0x2710 there is a thumbnail for the scope's gallery: `u16 width`, `u16 height` (75×36), then RGB565 pixels, **little-endian**, top row first.
- **biSizeImage:** the field is fixed at 0xBB800 and is wrong, but image programs ignore it.

## Other files and USB behaviour
- **`number_table.sys`:** `/Waveform/number_table.sys` and `/Screenshots/number_table.sys` are hidden files. They hold a u16 with the number of files, then a list of u16 with the numbers in use. They explain why the numbering restarts after a deletion.
- **Files deleted from the computer:** the scope removes them from its own list when its gallery is opened.
- **USB mode:** from the "USB sharing" menu the scope shows up only as a USB disk (mass storage, VID:PID 0483:5720). While connected it does not acquire and accepts no commands: there is no SCPI and no serial port.
- **macOS:** on macOS the scope hangs on the large reads the system normally issues. Reading in 4 kB blocks with the cache disabled (`F_NOCACHE`) always works.
