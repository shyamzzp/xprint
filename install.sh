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

STEP=0
STEP_TOTAL=7
step() { STEP=$((STEP+1)); printf '\n\033[1;36m[%d/%d]\033[0m \033[1m%s\033[0m\n' "$STEP" "$STEP_TOTAL" "$*"; }
say()  { printf '\033[1;36m  ->\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  ! \033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERR\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
# run: echo the command dimmed, then execute it with output streaming through
run()  { printf '\033[2m    $ %s\033[0m\n' "$*"; "$@"; }

# ---- detect platform -------------------------------------------------------
step "Detecting platform"
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM=mac ;;
  Linux)  PLATFORM=linux ;;
  *) die "unsupported OS: $OS (mac/linux only)" ;;
esac
ok "$PLATFORM ($(uname -m))"

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
    say "missing: ${need[*]}, installing via brew (live output below)"
    run brew install "${need[@]}"
  else
    ok "all brew prereqs already present (git, python, libusb)"
  fi
}

install_prereqs_linux() {
  local SUDO=""
  [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  if have apt-get; then
    say "pkg manager: apt (live output below)"
    run $SUDO apt-get update
    run $SUDO apt-get install -y python3 python3-venv python3-pip git libusb-1.0-0
  elif have dnf; then
    say "pkg manager: dnf (live output below)"
    run $SUDO dnf install -y python3 python3-pip git libusbx
  elif have pacman; then
    say "pkg manager: pacman (live output below)"
    run $SUDO pacman -Sy --noconfirm python git libusb
  else
    die "no supported package manager (apt/dnf/pacman). Install python3, git, libusb manually."
  fi
}

step "Installing prerequisites"
if [ "$PLATFORM" = mac ]; then install_prereqs_mac; else install_prereqs_linux; fi

# ---- validate prerequisites ------------------------------------------------
step "Validating prerequisites"
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
step "Fetching xprint source"
if [ -d "$INSTALL_DIR/.git" ]; then
  say "existing checkout found, syncing to latest: $INSTALL_DIR"
  # Managed checkout, not for hand edits. Force it to match origin/main so an
  # older installer's local tweaks can't block the update with a merge abort.
  run git -C "$INSTALL_DIR" fetch --depth 1 origin main
  run git -C "$INSTALL_DIR" reset --hard origin/main
  run git -C "$INSTALL_DIR" clean -fd
else
  say "cloning $REPO"
  say "  -> $INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  run git clone --depth 1 --progress "$REPO" "$INSTALL_DIR"
fi

# ---- venv + python deps ----------------------------------------------------
step "Creating venv + installing python deps"
say "python venv: $INSTALL_DIR/.venv"
run python3 -m venv "$INSTALL_DIR/.venv"
run "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
say "installing: $(tr '\n' ' ' < "$INSTALL_DIR/requirements.txt")"
run "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
say "verifying deps import"
run "$INSTALL_DIR/.venv/bin/python" -c 'import escpos, usb, PIL; print("escpos, pyusb, Pillow OK")' \
  || die "python deps failed to import"
ok "deps installed + import cleanly"

# ---- build a launcher (keeps the checkout pristine) ------------------------
# NOTE: do NOT edit xprint.py's shebang here. Mutating the tracked file dirties
# the git checkout and makes the next run's update abort. Instead ship a tiny
# wrapper that runs the script with the venv's Python.
step "Wiring up the global command"
LAUNCHER="$INSTALL_DIR/.bin/xprint"
mkdir -p "$INSTALL_DIR/.bin"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/xprint.py" "\$@"
EOF
chmod +x "$LAUNCHER"
ok "launcher: $LAUNCHER"

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
run ln -sf "$LAUNCHER" "$BINDIR/xprint"
ok "symlinked $BINDIR/xprint -> $LAUNCHER"

# ---- final validation ------------------------------------------------------
step "Done - final check"
if have xprint; then
  ok "xprint on PATH: $(command -v xprint)"
else
  warn "$BINDIR not on PATH. Add it:"
  warn "  echo 'export PATH=\"$BINDIR:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
fi

# show the full command list so the user knows how to use it
printf '\n\033[1m--- xprint commands ---\033[0m\n'
"$LAUNCHER" --help || true

printf '\n\033[1;32mReady.\033[0m  try:  echo "hello" | xprint\n'
echo "See the command list above, or run 'xprint --help' any time."
echo "note: set your printer USB IDs at the top of $INSTALL_DIR/xprint.py if it is not the default clone."
