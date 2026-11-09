#!/usr/bin/env bash
# One-shot setup on Ubuntu 24.04: KiCad 9 (+ libraries), Java 25, Freerouting,
# and a virtualenv that can see KiCad's pcbnew module.
set -euo pipefail
cd "$(dirname "$0")/.."

SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"

$SUDO add-apt-repository -y ppa:kicad/kicad-9.0-releases
$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends \
  kicad kicad-footprints kicad-symbols openjdk-25-jre-headless python3-venv

./scripts/get_freerouting.sh

# --system-site-packages exposes the distro's `pcbnew` module (installed by KiCad).
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[dev]'

echo
echo "Done. If 'java -version' is older than 25, add this to your shell profile:"
echo "  export JAVA=/usr/lib/jvm/java-25-openjdk-amd64/bin/java"
echo "Then: source .venv/bin/activate && pcbforge build designs/blinky.py"
