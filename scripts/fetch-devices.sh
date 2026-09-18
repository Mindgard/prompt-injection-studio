#!/usr/bin/env bash
# Fetch the device-side firmware repository.
#
# This is the counterpart to the host-side drivers in pistudio/hardware/. It
# is a separate repository because it is Flipper Zero C firmware, which is not
# installable as a Python package.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f .gitmodules ]; then
  echo "error: .gitmodules not found; run this from a git checkout" >&2
  exit 1
fi

echo "Fetching device repositories..."
git submodule sync --recursive
git submodule update --init --recursive

echo
echo "Flipper Zero firmware: vendor/flipper-field-kit"
echo "  Build and flash:  cd vendor/flipper-field-kit && ufbt launch"
