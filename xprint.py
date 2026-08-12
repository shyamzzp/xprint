#!/usr/bin/env python3
"""Print stdin (or file args) to an Xprinter 58mm thermal printer over USB.

Two modes:
  NATIVE (default) - printer's built-in font. Dark + uniform, fast. Fixed font.
  RASTER (-r)      - text rendered to a bitmap. Any font/size, but lighter.

Usage:
    echo "hi" | xprint                     # native small Font B (default)
    echo "hi" | xprint --nfont a           # native big font
    echo "hi" | xprint --scale 2           # native 2x bigger
    echo "hi" | xprint -r                  # raster, Courier size 24
    echo "hi" | xprint -r -s 28 -f menlo   # raster, custom size/font
    xprint file.txt                        # print a file
    xprint --retract 3                     # reverse-feed 3 lines: pull paper back in
    xprint -t                              # TELETYPE: prints each line live as it fills
    xprint                                 # INTERACTIVE: paste text, blank line prints
"""
import os
import sys
import datetime
import subprocess
from escpos.printer import Usb
from PIL import Image, ImageDraw, ImageFont

# --- Printer USB identity ------------------------------------------------
# Find yours with `ioreg -p IOUSB -l | grep -i idVendor -A1` (macOS) or
# `lsusb` (Linux). Endpoints from `lsusb -v` / pyusb enumeration (see README).
VENDOR, PRODUCT, IFACE = 0x0483, 0x070b, 0
OUT_EP, IN_EP = 0x02, 0x81
WIDTH = 384                       # 58mm printable width in dots
DEFAULT_SIZE = 24

# Font paths below are macOS defaults; edit for your OS (see README).
FONTS = {                          # "path" or "path#faceindex" (for .ttc bold faces)
    "menlo":      "/System/Library/Fonts/Menlo.ttc#1",   # Bold
    "typewriter": "/System/Library/Fonts/Supplemental/AmericanTypewriter.ttc",
    "courier":    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    "courier-reg":"/System/Library/Fonts/Supplemental/Courier New.ttf",
    "monaco":     "/System/Library/Fonts/Monaco.ttf",
}
DEFAULT_FONT = "courier"
LINE_SPACING = 1.0                # vertical gap between lines


def parse_args(argv):
    size, font, files = DEFAULT_SIZE, DEFAULT_FONT, []
    native, nfont, scale = True, "b", 1      # DEFAULT: native ESC/POS text, small Font B
    header = True
    each = False                             # each Enter prints its line immediately
    feed = 3                                 # blank lines fed after each print
    retract_n = 0                            # >0: reverse-feed N lines then exit
    stream = False                           # teletype: auto-print each line as it fills
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-s", "--size"):
            size = int(argv[i + 1]); i += 2
        elif a in ("-f", "--font"):
            font = argv[i + 1]; i += 2
        elif a in ("-r", "--raster"):        # switch to custom-font bitmap mode
            native = False; i += 1
        elif a in ("-n", "--native"):
            native = True; i += 1
        elif a == "--nfont":                 # native built-in font: a (big) or b (small)
            nfont = argv[i + 1]; i += 2
        elif a == "--scale":                 # native size multiplier 1..8
            scale = int(argv[i + 1]); i += 2
        elif a == "--no-header":
            header = False; i += 1
        elif a in ("-e", "--each"):          # line-at-a-time: Enter prints immediately
            each = True; i += 1
        elif a == "--feed":                  # blank lines fed after each print
            feed = int(argv[i + 1]); i += 2
        elif a in ("--retract", "--reverse"):  # reverse-feed N lines, then exit
            retract_n = int(argv[i + 1]); i += 2
        elif a in ("-t", "--stream", "--teletype"):  # live: print each line as it fills
            stream = True; i += 1
        else:
            files.append(a); i += 1
    return size, font, files, native, nfont, scale, header, each, feed, retract_n, stream


def read_input(files):
    if files:
        return "".join(open(f).read() for f in files)
    return sys.stdin.read()


def now_header():
    """Return (date_str, day_str) e.g. ('10th Aug, 2026', 'Monday')."""
    d = datetime.datetime.now()
    day = d.day
    suf = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    date_str = f"{day}{suf} {d.strftime('%b')}, {d.year}"
    return date_str, d.strftime("%A")


def wrap(font, lines):
    """Fold lines wider than WIDTH dots at character boundaries."""
    cw = font.getbbox("M")[2] or 1          # monospace char width
    maxc = max(1, WIDTH // cw)
    out = []
    for ln in lines:
        if not ln:
            out.append("")
        while ln:
            out.append(ln[:maxc]); ln = ln[maxc:]
    return out


def load_font(font_key, size):
    spec = FONTS.get(font_key, font_key)   # accept preset name or full path
    path, _, idx = spec.partition("#")     # optional "#faceindex" for .ttc
    return ImageFont.truetype(path, size, index=int(idx) if idx else 0)


def strike(draw, xy, text, font):
    """Single pass = lighter, thinner strokes."""
    draw.text(xy, text, font=font, fill=0)


def render(text, size, font_key, header=None):
    font = load_font(font_key, size)
    lines = wrap(font, text.split("\n"))
    ascent, descent = font.getmetrics()
    # measure true tallest glyph box so descenders never clip between lines
    bbox = font.getbbox("gjpqyÅ")
    glyph_h = bbox[3] - bbox[1]
    lh = int(max(ascent + descent, glyph_h) * LINE_SPACING) + 2

    # header: date left + weekday right, smaller font, then a gap
    hfont = hh = None
    if header:
        hfont = load_font(font_key, max(12, size * 2 // 3))
        ha, hd = hfont.getmetrics()
        hh = ha + hd + 28                           # header row height + gap under it

    pad = 4                                          # bottom breathing room
    top = 8                                          # small top margin
    h = top + (hh or 0) + max(lh * len(lines), lh) + pad
    h = ((h + 23) // 24) * 24                         # round up to 24-dot band (printer req)
    img = Image.new("1", (WIDTH, h), 1)             # 1 = white bg
    draw = ImageDraw.Draw(img)
    y = top
    if header:
        date_str, day_str = header
        strike(draw, (0, y), date_str, hfont)                       # left
        dw = hfont.getbbox(day_str)[2]
        strike(draw, (WIDTH - dw, y), day_str, hfont)               # right-aligned
        y += hh
    for ln in lines:
        strike(draw, (0, y), ln, font)
        y += lh
    return img


def open_printer():
    p = Usb(VENDOR, PRODUCT, IFACE, in_ep=IN_EP, out_ep=OUT_EP)
    p.timeout = 5000
    # This clone stalls (USB Pipe error) on one big bulk write, but multiple
    # raster commands print gibberish. So: ONE raster command, USB bulk writes
    # split into small chunks the buffer can absorb.
    orig_raw = p._raw
    def chunked_raw(msg, _n=3072):
        for i in range(0, len(msg), _n):
            orig_raw(msg[i:i + _n])
    p._raw = chunked_raw
    return p


def do_print(p, body, cfg, show_header=True):
    """Print one chunk of text using the current config dict."""
    if not body.strip():
        return
    header = now_header() if (cfg["header"] and show_header) else None
    if cfg["native"]:
        if header:
            date_str, day_str = header
            width = 42                       # Font B chars per 58mm line
            gap = max(1, width - len(date_str) - len(day_str))
            p.set(font="b", width=1, height=1, bold=False)     # match body weight
            p.text(date_str + " " * gap + day_str + "\n\n")    # blank line = gap under header
        p.set(font=cfg["nfont"], width=cfg["scale"], height=cfg["scale"],
              bold=False, double_width=False)
        p.text(body if body.endswith("\n") else body + "\n")
    else:
        if not body.endswith("\n"):        # last line full, unclipped
            body += "\n"
        img = render(body, cfg["size"], cfg["font"], header=header)
        p.image(img, impl="bitImageRaster")  # single contiguous raster stream
    p.text("\n" * cfg.get("feed", 3))   # feed so last line clears the head; :feed N to tune


def retract(p, n):
    """Reverse-feed n lines: pull paper back into the printer (undo a feed).

    Sends ESC/POS 'ESC e n' (print and reverse feed n lines). Many cheap
    Xprinter 58mm clones lack a reverse-feed motor and silently ignore this;
    if the paper does not move, your unit is one of those.
    """
    n = max(0, min(n, 255))
    p._raw(b"\x1b\x65" + bytes([n]))


def self_update():
    """Pull the latest xprint into this checkout and refresh its deps.

    Same effect as re-running the curl installer, but from inside the tool:
    fetch + hard-reset to origin/main, then reinstall requirements into the
    venv. The running process keeps the old code, so restart xprint after.
    """
    here = os.path.dirname(os.path.realpath(__file__))
    if not os.path.isdir(os.path.join(here, ".git")):
        print("not a git checkout, can't self-update. "
              "Reinstall with the curl one-liner from the README.")
        return

    def rev():
        r = subprocess.run(["git", "-C", here, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True)
        return r.stdout.strip()

    def sh(*cmd):
        print("  $", " ".join(cmd))
        subprocess.run(cmd, check=True)

    print(f"updating xprint in {here}")
    try:
        old = rev()
        sh("git", "-C", here, "fetch", "--depth", "1", "origin", "main")
        sh("git", "-C", here, "reset", "--hard", "origin/main")
        sh("git", "-C", here, "clean", "-fd")
        new = rev()
        venv_py = os.path.join(here, ".venv", "bin", "python")
        py = venv_py if os.path.exists(venv_py) else sys.executable
        sh(py, "-m", "pip", "install", "-q", "-r",
           os.path.join(here, "requirements.txt"))
    except subprocess.CalledProcessError as e:
        print(f"update failed: {e}")
        return

    if old == new:
        print(f"already up to date ({new}).")
    else:
        print(f"updated {old} -> {new}. Restart xprint to load the new version.")


HELP = """\
Interactive xprint. Paste/type text; a BLANK line prints the buffer.
Commands (start with ':'):
  :native            dark uniform built-in font (default)
  :raster            custom-font bitmap mode (any font/size, lighter)
  :nfont a|b         native font: a=big, b=small
  :scale N           native size multiplier 1..8
  :font NAME         raster font (courier/typewriter/menlo/monaco/path)
  :size N            raster point size
  :header on|off     date + weekday line at top (default on)
  :feed N            blank lines fed after each print (default 3)
  :retract N         reverse-feed N lines: pull paper back in (undo a feed)
  :update / :upgrade update xprint to the latest version (git pull + deps)
  :status            show current settings
  :help              this help
  :quit / Ctrl-D     exit"""


def status(cfg):
    hdr = "hdr:on" if cfg["header"] else "hdr:off"
    if cfg["native"]:
        return f"[native] font={cfg['nfont']} scale={cfg['scale']}x {hdr}"
    return f"[raster] font={cfg['font']} size={cfg['size']} {hdr}"


def do_command(line, cfg, p=None):
    """Handle a ':' command. Return False to quit, True to continue."""
    parts = line[1:].split()
    if not parts:
        return True
    cmd, arg = parts[0], (parts[1] if len(parts) > 1 else None)
    if cmd in ("quit", "q", "exit"):
        return False
    elif cmd == "retract" and arg:         # reverse-feed: pull paper back in
        if p is not None:
            retract(p, int(arg))
        print(f"retracted {arg} line(s)")
        return True
    elif cmd in ("update", "upgrade"):     # self-update to latest, no curl needed
        self_update()
        return True
    elif cmd == "help":
        print(HELP)
    elif cmd == "status":
        print(status(cfg))
    elif cmd == "native":
        cfg["native"] = True
    elif cmd == "raster":
        cfg["native"] = False
    elif cmd == "nfont" and arg:
        cfg["nfont"] = arg
    elif cmd == "scale" and arg:
        cfg["scale"] = int(arg)
    elif cmd == "font" and arg:
        cfg["font"] = arg
    elif cmd == "size" and arg:
        cfg["size"] = int(arg)
    elif cmd == "header" and arg:
        cfg["header"] = arg.lower() in ("on", "true", "1", "yes")
    elif cmd == "feed" and arg:
        cfg["feed"] = int(arg)
    else:
        print(f"? unknown command ':{cmd}' (:help)")
        return True
    print(status(cfg))
    return True


def interactive(p, cfg):
    print("xprint interactive. :help for commands, blank line prints, Ctrl-D quits.")
    print(status(cfg))
    buf = []
    first = [True]                          # header only on the session's first print
    while True:
        try:
            line = input("… " if buf else "xprint> ")
        except EOFError:
            print()
            break
        if line.startswith(":"):
            if not do_command(line, cfg, p):
                break
            continue
        if line == "":                      # blank line = print buffer
            if buf:
                do_print(p, "\n".join(buf), cfg, show_header=first[0])
                first[0] = False            # date/day printed once per session
                print(f"printed {len(buf)} line(s) {status(cfg)}")
                buf = []
            continue
        buf.append(line)
    if buf:                                 # flush on exit
        do_print(p, "\n".join(buf), cfg, show_header=first[0])
        print(f"printed {len(buf)} line(s)")


def each_line(p, cfg):
    """Line-at-a-time: every Enter prints that line immediately."""
    print("xprint each-line. Type text, Enter prints it. :help for commands, Ctrl-D quits.")
    print(status(cfg))
    first = [True]                          # header only on the session's first print
    while True:
        try:
            line = input("xprint> ")
        except EOFError:
            print()
            break
        if line.startswith(":"):
            if not do_command(line, cfg, p):
                break
            continue
        if line == "":                      # blank Enter = paper feed only
            p.text("\n")
            continue
        do_print(p, line, cfg, show_header=first[0])
        first[0] = False


def stream_mode(p, cfg):
    """Teletype: read keystrokes live and print each line the instant it fills
    the paper width (word-wrapped so words are not split), then keep going for
    the next line. Enter forces a line early; Ctrl-D / Ctrl-C flushes + exits.

    Native ESC/POS text only (fixed-width, so we can count chars per line).
    """
    import termios, tty

    if not sys.stdin.isatty():
        die("stream mode needs an interactive terminal (don't pipe into -t)")

    # chars per 58mm line for the built-in fonts, divided by the size multiplier
    per_line = {"a": 32, "b": 42}.get(cfg["nfont"], 42)
    width = max(1, per_line // max(1, cfg["scale"]))

    # header once at the top, then lock in the body font
    if cfg["header"]:
        date_str, day_str = now_header()
        gap = max(1, 42 - len(date_str) - len(day_str))
        p.set(font="b", width=1, height=1, bold=False)
        p.text(date_str + " " * gap + day_str + "\n\n")
    p.set(font=cfg["nfont"], width=cfg["scale"], height=cfg["scale"], bold=False)

    def emit(s):
        p.text(s + "\n")                     # one paper line, no extra feed

    print(f"xprint stream. Type away — each line prints at {width} chars "
          f"(or on Enter). Ctrl-D to finish.\n")

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    line = ""
    try:
        tty.setcbreak(fd)                    # chars arrive without waiting for Enter
        while True:
            ch = sys.stdin.read(1)
            if ch in ("", "\x04"):           # EOF / Ctrl-D
                break
            if ch == "\x03":                 # Ctrl-C
                raise KeyboardInterrupt
            if ch in ("\r", "\n"):           # Enter: print what we have now
                sys.stdout.write("\r\n"); sys.stdout.flush()
                emit(line); line = ""
                continue
            if ch in ("\x7f", "\b"):         # backspace
                if line:
                    line = line[:-1]
                    sys.stdout.write("\b \b"); sys.stdout.flush()
                continue
            if ch < " ":                     # ignore other control chars
                continue
            line += ch
            sys.stdout.write(ch); sys.stdout.flush()
            if len(line) >= width:           # line full -> print it now
                cut = line.rfind(" ")
                if cut <= 0:                 # no space: hard-break the long word
                    head, line = line, ""
                else:                        # word-wrap: keep trailing word for next line
                    head, line = line[:cut], line[cut + 1:]
                emit(head)
                sys.stdout.write("\r\n" + line); sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    if line.strip():                         # flush the last partial line
        emit(line)
    p.text("\n" * cfg.get("feed", 3))        # feed so the last line clears the head
    print()


def main():
    size, font, files, native, nfont, scale, header, each, feed, retract_n, stream = parse_args(sys.argv[1:])
    cfg = {"size": size, "font": font, "native": native,
           "nfont": nfont, "scale": scale, "header": header, "feed": feed}
    p = open_printer()

    if retract_n > 0:                      # undo a feed: pull paper back, then exit
        retract(p, retract_n)
        return

    if stream:                             # teletype: native only, prints as you type
        cfg["native"] = True
        stream_mode(p, cfg)
        return

    # Interactive when no files and stdin is a terminal; else one-shot.
    if not files and sys.stdin.isatty():
        if each:
            each_line(p, cfg)
        else:
            interactive(p, cfg)
    else:
        do_print(p, read_input(files), cfg)


if __name__ == "__main__":
    main()
