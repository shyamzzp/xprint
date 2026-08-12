# xprint

**Install (macOS / Linux):**

```bash
curl -fsSL https://shyamzzp.github.io/xprint/install.sh | bash
```

Print text to a cheap **58mm Xprinter ESC/POS thermal printer** from macOS (or Linux) over USB, straight from the terminal.

macOS has no working driver for these no-name thermal printers: raw CUPS queues were removed, only Generic PostScript/PCL PPDs ship (which the printer can't read), and there's no vendor PPD. So `xprint` talks to the printer **directly over USB** via [`python-escpos`](https://github.com/python-escpos/python-escpos) + `libusb`, no CUPS queue needed.

## Features

- **Two print modes**
  - **Native** (default): the printer's built-in font. Dark, uniform, fast. Font is fixed (built-in A/B, integer scaling only).
  - **Raster** (`-r`): text rendered to a bitmap with any TrueType font at any size. More flexible, lighter/softer than native.
- **Date + weekday header** on each print: date left (`10th Aug, 2026`), weekday right (`Monday`), in a smaller font.
- **Interactive session**: run `xprint` with no args, paste text, blank line prints. Header prints once at the top of the session.
- **Teletype / stream** (`-t`): prints each line live the moment your typing fills the paper width, word-wrapped, like an old teletype.
- **Each-line** (`-e`): every Enter prints that one line immediately.
- **Reverse feed** (`--retract N`): try to pull paper back into the printer (hardware permitting).
- **Auto-wrap** of long lines, descender-safe line height, and a chunked USB writer that works around this clone's tiny buffer (single big write → USB pipe error; multiple raster commands → gibberish).

## Requirements

- Python 3.9+
- `libusb`
  - macOS: `brew install libusb`
  - Debian/Ubuntu: `sudo apt install libusb-1.0-0`
- Python packages: `python-escpos`, `pyusb`, `Pillow`

## Install

One command on a fresh macOS or Linux machine. It installs prerequisites (git,
python3, libusb), validates them, clones the repo, builds a venv, and puts an
`xprint` command on your `PATH`. Shows live `[n/7]` step progress. Idempotent:
safe to re-run to update.

```bash
curl -fsSL https://shyamzzp.github.io/xprint/install.sh | bash
```

Then smoke test:

```bash
echo "it works" | xprint
```

- **macOS** needs [Homebrew](https://brew.sh) first (the installer stops with the link if it's missing).
- If you see `xprint: command not found`, the symlink dir isn't on your `PATH`; the installer prints the exact `export PATH=...` line to fix it.
- Env overrides: `XPRINT_DIR` (install location, default `~/.local/share/xprint`), `XPRINT_BIN` (symlink dir).

> The install URL is served by **GitHub Pages** (`username.github.io/repo/install.sh`),
> easy to recall from the repo name and refreshed on every push. Two equivalents
> if you ever need them:
>
> ```bash
> # GitHub API (always current, no cache lag)
> curl -fsSL -H "Accept: application/vnd.github.raw" \
>   https://api.github.com/repos/shyamzzp/xprint/contents/install.sh?ref=main | bash
>
> # raw.githubusercontent (CDN-cached a few minutes after a push)
> curl -fsSL https://raw.githubusercontent.com/shyamzzp/xprint/main/install.sh | bash
> ```

<details>
<summary>Manual install (no installer script)</summary>

```bash
git clone https://github.com/shyamzzp/xprint.git
cd xprint
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo "hello" | .venv/bin/python xprint.py
# optional global command:
ln -sf "$(pwd)/xprint.py" /opt/homebrew/bin/xprint   # or any dir on PATH
```
</details>

## Command reference

### Modes: how you feed text

| Command | Description |
|---------|-------------|
| `echo "text" \| xprint` | Print piped text (one-shot). |
| `xprint file.txt` | Print a file. |
| `xprint` | Interactive: paste/type, a blank-line Enter prints the buffer. |
| `xprint -e` | Each-line: every Enter prints that line immediately. |
| `xprint -t` | Teletype: prints each line live as your typing fills the paper width. |
| `xprint --retract N` | Reverse-feed N lines, then exit (pull paper back in). |

### Flags

| Flag | Description |
|------|-------------|
| `--nfont b` | Native small built-in font (**default**, ~42 chars/line). |
| `--nfont a` | Native big built-in font (~32 chars/line). |
| `--scale N` | Native size multiplier, 1–8. |
| `-r`, `--raster` | Raster mode: bitmap render with any TrueType font. |
| `-f NAME`, `--font NAME` | Raster font: preset (`courier`/`courier-reg`/`menlo`/`monaco`/`typewriter`) or a `.ttf`/`.otf` path. |
| `-s N`, `--size N` | Raster point size (default 24). |
| `-n`, `--native` | Force native mode (default). |
| `--no-header` | Skip the date + weekday header. |
| `--feed N` | Blank lines fed after each print (default 3). |
| `--retract N`, `--reverse N` | Reverse-feed N lines (most clones ignore it; no reverse motor). |
| `-e`, `--each` | Each-line mode (Enter prints the line). |
| `-t`, `--stream`, `--teletype` | Teletype mode. |
| `-h`, `--help` | Print usage + all commands, then exit. |

## Usage

```bash
# one-shot
echo "hello world" | xprint          # native small font (default), with date header
xprint notes.txt                     # print a file
echo "big" | xprint --nfont a        # native big built-in font
echo "2x"  | xprint --scale 2        # native double size
echo "hi"  | xprint --no-header      # skip the date/weekday header
xprint --retract 3                   # reverse-feed 3 lines: pull paper back in (undo a feed)
xprint -t                            # teletype: prints each line live as you fill the paper width

# raster mode (custom fonts / sizes)
echo "hi"  | xprint -r                       # Courier, size 24
echo "hi"  | xprint -r -s 28 -f menlo        # Menlo bold, size 28
echo "hi"  | xprint -r -f /path/to/font.ttf  # any TrueType/OTF
```

### Teletype / stream mode (`-t`)

```bash
xprint -t
```

Prints **as you type**, one paper line at a time. The instant your typing fills a
paper-width line (Font B ≈ 42 chars, Font A ≈ 32, divided by `--scale`), that line
prints immediately and you keep typing into the next one, like an old teletype.

- **Word-wrapped**: a line breaks at the last space, so words are never split.
- **Enter** forces the current line to print early.
- **Backspace** edits the not-yet-printed line.
- The date/weekday header prints **once** at the top (unless `--no-header`).
- **Ctrl-D** (or Ctrl-C) flushes the last partial line and exits.
- Native font only (fixed-width is what lets us count chars per line). Combine with
  `--nfont a`, `--scale N`, `--no-header`, `--feed N`.

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
| `:feed N`        | blank lines fed after each print                  |
| `:retract N`     | reverse-feed N lines: pull paper back in          |
| `:update` / `:upgrade` | update xprint to the latest version (git pull + deps) |
| `:status`        | show current settings                             |
| `:help`          | command list                                      |
| `:quit`          | exit (Ctrl-D also works)                          |

## Updating

From inside an interactive session, just type:

```
:update      (or :upgrade)
```

It pulls the latest code into your checkout (fetch + hard-reset to `origin/main`)
and reinstalls the Python deps, no `curl` needed. The running process keeps the
old code, so **restart `xprint`** afterwards to use the new version.

Equivalent from the shell (re-runs the installer, also works to update):

```bash
curl -fsSL https://shyamzzp.github.io/xprint/install.sh | bash
```

Note: the checkout at `~/.local/share/xprint` is managed. `:update` (and the
installer) hard-reset it to `origin/main`, so any local edits you make there,
e.g. custom `FONTS` or USB IDs, are overwritten on update. Keep a copy if you
customize.

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
- **Reverse feed (`--retract N` / `:retract N`)** sends ESC/POS `ESC e n` to pull paper back into the printer. Many cheap Xprinter 58mm clones have no reverse-feed motor and silently ignore it; if the paper does not move, your unit is one of those.
- **`USB device not found` / `Device (1155, 1803) not found`**: printer is off or unplugged. Power it and connect USB, then retry.
- **`USBError: Access denied` / `Pipe error`**: another process holds the device (e.g. a running interactive session) or it stalled. Close other users and/or reset it:
  ```bash
  ~/.local/share/xprint/.venv/bin/python -c "import usb.core; usb.core.find(idVendor=0x0483, idProduct=0x070b).reset()"
  ```

## License

MIT, see [LICENSE](LICENSE).
