# FNIRSI DPOX180H: download, viewer and decoding of saved files

Tools for the FNIRSI DPOX180H handheld oscilloscope (firmware V40), tested on macOS:

- **Download:** copies the files off the scope over USB without the hangs you get with the Finder.
- **File decoding:** decodes the saved waveforms (`.wav`) correctly and exports them to CSV.
- **Browser viewer:** thumbnail gallery, scope-like scales, cursors, zoom, and **I²C**, **UART** and **1-Wire** bus decoding.

*Versione italiana: [README.it.md](README.it.md).*

**Not affiliated with FNIRSI.** An independent project, written to read my own measurement files. FNIRSI is a trademark of its owner.

## Requirements

- Python 3.9 or later, no external libraries.
- macOS to download from the scope: the script uses `mount`, `diskutil` and uncached reads. Reading files and the viewer work anywhere.
- A recent browser.

## Usage

On the scope: settings → **USB sharing**, then plug in the cable.

```bash
python3 fnirsi.py viewer
```

The viewer opens in the browser, with a gallery of the files on the scope.

- **Gallery:**
  - Thumbnails labelled **new** or **on this computer**.
  - **Download selected** copies the files and opens the waveforms in the viewer straight away.
  - **Delete from scope** asks for confirmation first.
  - **Eject** ejects the scope's disk.
- **Viewer:**
  - V/div and s/div as on the scope (1-2-5 steps, automatic units), zero position, 12 × 8 grid.
  - Separate or overlaid traces.
  - Acquisition choice: each file holds more than one, and the first is the one the screen showed.
  - Zoom by dragging on the plot; scroll with the bar, ◀ ▶ or the trackpad.
  - Δt and ΔV cursors.
  - CSV and PNG export.
- **Bus decoding:**
  - **I²C:** START, STOP, repeated start, 7-bit address, R/W, ACK and NACK.
  - **UART:** TX and RX, automatic baud rate, data bits, parity, stop bits, TTL or RS-232 levels.
  - **1-Wire:** reset, presence, ROM and DS18B20 commands, CRC, temperature.

The viewer also works when you open `viewer.html` directly in the browser. It then reads files you open or drop on it, without the scope gallery.

Other commands:

```bash
python3 fnirsi.py download --csv --eject
```

```bash
python3 fnirsi.py info FILE.wav
```

```bash
python3 fnirsi.py csv --acquisition 2 FILE.wav
```

Downloaded files go to `measurements/fnirsi_YYYYMMDD`, in the folder that contains this project. Use `--dest DIR` to change it.

To try the decoders without a scope, open the files in `examples/` in the viewer.

## Contents

| Path | What it is |
|---|---|
| `fnirsi.py` | download, decoding, CSV and the viewer's server |
| `viewer.html` | the viewer |
| `FILE_FORMAT.md` | format of the `.wav` and `.bmp` files, behaviour over USB |
| `examples/` | synthetic `.wav` files with I²C, UART and 1-Wire traffic to try the decoders |
| `examples/generators/` | the scripts that made them |

## Good to know

- **Hangs on macOS:** the scope hangs on large reads. The script reads 4 kB at a time without cache, always in a separate process with a timeout. If a read hangs, unplug and replug the cable.
- **USB:** the scope only offers a USB disk (mass storage): no SCPI, no serial port, no remote acquisition.
- **Bus decoding:** tested on the synthetic files in `examples/`. As on any scope, pick the protocol to match the signal: a decoder will read something even from a signal that is not a bus.

## License

MIT, see `LICENSE`.
