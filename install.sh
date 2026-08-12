#!/usr/bin/env bash
#
# xprint one-shot installer.
# Installs prerequisites, validates them, then installs xprint as a global command.
#
#   curl -fsSL https://raw.githubusercontent.com/shyamzzp/xprint/main/install.sh | bash
#
# Env overrides:
#   XPRINT_DIR   install location   (default: ~/.local/share/xprint)
#   XPRINT_BIN   symlink target dir  (default: first writable PATH dir found)
#
set -euo pipefail

REPO="https://github.com/shyamzzp/xprint.git"
INSTALL_DIR="${XPRINT_DIR:-$HOME/.local/share/xprint}"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  ! \033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERR\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---- detect platform -------------------------------------------------------
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM=mac ;;
  Linux)  PLATFORM=linux ;;
  *) die "unsupported OS: $OS (mac/linux only)" ;;
esac
say "platform: $PLATFORM"

# ---- install prerequisites -------------------------------------------------
install_prereqs_mac() {
  if ! have brew; then
    die "Homebrew not found. Install it first: https://brew.sh  then re-run."
  fi
  local need=()
  have git      || need+=(git)
  have python3  || need+=(python)
  # libusb has no CLI; check via brew list
  brew list libusb >/dev/null 2>&1 || need+=(libusb)
  if [ "${#need[@]}" -gt 0 ]; then
    say "brew install: ${need[*]}"
    brew install "${need[@]}"
  else
    ok "brew prereqs already present"
  fi
}

install_prereqs_linux() {
  local SUDO=""
  [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  if have apt-get; then
    say "apt-get install prerequisites"
    $SUDO apt-get update -qq
    $SUDO apt-get install -y python3 python3-venv python3-pip git libusb-1.0-0
  elif have dnf; then
    say "dnf install prerequisites"
    $SUDO dnf install -y python3 python3-pip git libusbx
  elif have pacman; then
    say "pacman install prerequisites"
    $SUDO pacman -Sy --noconfirm python git libusb
  else
    die "no supported package manager (apt/dnf/pacman). Install python3, git, libusb manually."
  fi
}

say "installing prerequisites"
if [ "$PLATFORM" = mac ]; then install_prereqs_mac; else install_prereqs_linux; fi

# ---- validate prerequisites ------------------------------------------------
say "validating prerequisites"
have git     || die "git missing after install"
have python3 || die "python3 missing after install"
PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
python3 -c 'import sys;raise SystemExit(0 if sys.version_info[:2]>=(3,9) else 1)' \
  || die "python3 >= 3.9 required, found $PYV"
python3 -m venv --help >/dev/null 2>&1 || die "python venv module missing (install python3-venv)"
ok "git $(git --version | awk '{print $3}')"
ok "python $PYV"
if [ "$PLATFORM" = mac ]; then
  brew list libusb >/dev/null 2>&1 && ok "libusb (brew)" || warn "libusb not confirmed"
else
  ldconfig -p 2>/dev/null | grep -q libusb-1.0 && ok "libusb-1.0" || warn "libusb-1.0 not confirmed"
fi

# ---- fetch / update repo ---------------------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
  say "updating existing checkout: $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only
else
  say "cloning into: $INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --depth 1 "$REPO" "$INSTALL_DIR"
fi

# ---- venv + python deps ----------------------------------------------------
say "creating venv + installing python deps"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
ok "python deps installed"

# validate the deps import
"$INSTALL_DIR/.venv/bin/python" -c 'import escpos, usb, PIL' \
  || die "python deps failed to import"
ok "deps import cleanly"

# ---- pin shebang at the venv interpreter -----------------------------------
say "pinning shebang to venv interpreter"
python3 - "$INSTALL_DIR/xprint.py" "$INSTALL_DIR/.venv/bin/python3" <<'PY'
import sys
path, interp = sys.argv[1], sys.argv[2]
lines = open(path).read().splitlines(keepends=True)
lines[0] = f"#!{interp}\n"
open(path, "w").writelines(lines)
PY
chmod +x "$INSTALL_DIR/xprint.py"

# ---- symlink onto PATH -----------------------------------------------------
pick_bindir() {
  if [ -n "${XPRINT_BIN:-}" ]; then echo "$XPRINT_BIN"; return; fi
  for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
    case ":$PATH:" in *":$d:"*) if [ -d "$d" ] && [ -w "$d" ]; then echo "$d"; return; fi ;; esac
  done
  echo "$HOME/.local/bin"
}
BINDIR="$(pick_bindir)"
mkdir -p "$BINDIR"
ln -sf "$INSTALL_DIR/xprint.py" "$BINDIR/xprint"
ok "symlinked $BINDIR/xprint"

# ---- final validation ------------------------------------------------------
say "done"
if have xprint; then
  ok "xprint on PATH: $(command -v xprint)"
else
  warn "$BINDIR not on PATH. Add it:"
  warn "  echo 'export PATH=\"$BINDIR:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
fi
printf '\n  try:  echo "hello" | xprint\n\n'
echo "note: set your printer USB IDs at the top of $INSTALL_DIR/xprint.py if it is not the default clone."
