#!/bin/sh
# Build RobotHelper.app, sign it with a stable identity and update /Applications in place.
# A stable bundle id + signing identity lets macOS keep the privacy permissions across updates.
set -e
cd "$(dirname "$0")/.."
ID="${SIGN_IDENTITY:-$(security find-identity -v -p codesigning | awk 'NR==1{print $2}')}"
OUT="${TMPDIR:-/tmp}/rh-dist"
.venv/bin/pyinstaller --clean --noconfirm --windowed --name RobotHelper \
  --osx-bundle-identifier app.robothelper.RobotHelper \
  --paths "$PWD" --collect-all robot_helper --collect-all pynput --collect-submodules keyring.backends \
  --icon "$PWD/robot_helper/assets/icon.icns" \
  --distpath "$OUT" --workpath "${TMPDIR:-/tmp}/rh-build" --specpath "${TMPDIR:-/tmp}/rh-build" \
  packaging/launch.py > "${TMPDIR:-/tmp}/rh-build.log" 2>&1
codesign --force --deep --sign "$ID" "$OUT/RobotHelper.app"
codesign --verify --deep "$OUT/RobotHelper.app"
pkill -f "RobotHelper.app/Contents/MacOS" || true
sleep 1
mkdir -p /Applications/RobotHelper.app
rsync -a --delete "$OUT/RobotHelper.app/" /Applications/RobotHelper.app/
echo "installed: $(codesign -dv /Applications/RobotHelper.app 2>&1 | grep -E 'Identifier=|Authority=' | head -2 | tr '\n' ' ')"
