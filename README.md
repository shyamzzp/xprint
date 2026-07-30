# xprint

Print text to a cheap **58mm Xprinter ESC/POS thermal printer** from macOS (or Linux) over USB, straight from the terminal.

macOS has no working driver for these no-name thermal printers: raw CUPS queues were removed, only Generic PostScript/PCL PPDs ship (which the printer can't read), and there's no vendor PPD. So `xprint` talks to the printer **directly over USB** via [`python-escpos`](https://github.com/python-escpos/python-escpos) + `libusb`, no CUPS queue needed.

## Features

- **Two print modes**
  - **Native** (default): the printer's built-in font. Dark, uniform, fast. Font is fixed (built-in A/B, integer scaling only).
  - **Raster** (`-r`): text rendered to a bitmap with any TrueType font at any size. More flexible, lighter/softer than native.
- **Date + weekday header** on each print: date left (`10th Aug, 2026`), weekday right (`Monday`), in a smaller font.
- **Interactive session**: run `xprint` with no args, paste text, blank line prints. Header prints once at the top of the session.
- **Auto-wrap** of long lines, descender-safe line height, and a chunked USB writer that works around this clone's tiny buffer (single big write → USB pipe error; multiple raster commands → gibberish).

## Requirements

- Python 3.9+
- `libusb`
  - macOS: `brew install libusb`
  - Debian/Ubuntu: `sudo apt install libusb-1.0-0`
- Python packages: `python-escpos`, `pyusb`, `Pillow`

## Install

```bash
git clone https://github.com/shyamzzp/xprint.git
cd xprint

# isolated venv (recommended)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# run
echo "hello" | .venv/bin/python xprint.py
```

### Make it a global `xprint` command

Point the script's shebang at your venv's Python (or install the deps globally), then symlink it onto your `PATH`:

```bash
# option A: keep the venv, hard-code its interpreter in the shebang
sed -i '' "1s|.*|#!$(pwd)/.venv/bin/python3|" xprint.py   # macOS
chmod +x xprint.py
ln -sf "$(pwd)/xprint.py" /opt/homebrew/bin/xprint         # or any dir on PATH
```

Now `xprint` works from anywhere.

## Usage

```bash
# one-shot
echo "hello world" | xprint          # native small font (default), with date header
xprint notes.txt                     # print a file
echo "big" | xprint --nfont a        # native big built-in font
echo "2x"  | xprint --scale 2        # native double size
echo "hi"  | xprint --no-header      # skip the date/weekday header

# raster mode (custom fonts / sizes)
echo "hi"  | xprint -r                       # Courier, size 24
echo "hi"  | xprint -r -s 28 -f menlo        # Menlo bold, size 28
echo "hi"  | xprint -r -f /path/to/font.ttf  # any TrueType/OTF
```

### Interactive session

```bash
xprint
```

- Type or **paste** text (multiple lines OK)
- Press **Enter on a blank line** to print the buffered text
- The date/weekday header prints **once**, at the top of the session
- **Ctrl-D** prints any leftover text and exits

Live commands (type at the prompt):

| Command          | Effect                                            |
|------------------|---------------------------------------------------|
| `:native`        | native built-in font mode (default)               |
| `:raster`        | custom-font bitmap mode                           |
| `:nfont a|b`     | native font: `a` = big, `b` = small               |
| `:scale N`       | native size multiplier (1–8)                      |
| `:font NAME`     | raster font (`courier`/`typewriter`/`menlo`/`monaco`/path) |
| `:size N`        | raster point size                                 |
| `:header on|off` | toggle the date/weekday header                    |
| `:status`        | show current settings                             |
| `:help`          | command list                                      |
| `:quit`          | exit (Ctrl-D also works)                          |

## Configuring for your printer

The USB IDs and endpoints at the top of `xprint.py` are for one common Xprinter 58mm clone:

```python
VENDOR, PRODUCT, IFACE = 0x0483, 0x070b, 0
OUT_EP, IN_EP = 0x02, 0x81
```

Find your printer's IDs:

- **macOS**: `ioreg -p IOUSB -l | grep -i -E "idVendor|idProduct|USB Product Name"`
- **Linux**: `lsusb` (IDs), `lsusb -v` (endpoints)

Or enumerate endpoints with pyusb:

```python
import usb.core
d = usb.core.find(idVendor=0x0483, idProduct=0x070b)
for cfg in d:
    for intf in cfg:
        for ep in intf:
            print(hex(ep.bEndpointAddress),
                  "IN" if ep.bEndpointAddress & 0x80 else "OUT")
```

Then update `VENDOR`, `PRODUCT`, `IFACE`, `OUT_EP`, `IN_EP`. On non-macOS, also update the `FONTS` paths to fonts that exist on your system.

## Notes

- **Thermal paper fades.** No ink, just heat-sensitive dye. Heat, sunlight, PVC sleeves, and oils erase it (weeks to months). Scan or photograph anything you need to keep.
- No paper cut is issued (these units usually have no auto-cutter); a few blank lines are fed so the last line clears the print head.
- If you hit `USBError: Access denied` / `Pipe error`, another process holds the device (e.g. a running interactive session) or it stalled — close other users and/or reset it: `python -c "import usb.core; usb.core.find(idVendor=0x0483, idProduct=0x070b).reset()"`.

## License

MIT — see [LICENSE](LICENSE).
