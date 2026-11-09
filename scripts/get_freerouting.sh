#!/usr/bin/env bash
# Download the Freerouting autorouter (needs Java 21+) into tools/freerouting.jar,
# verifying Maven Central's published SHA-1.
set -euo pipefail

VERSION="${FREEROUTING_VERSION:-2.4.1}"
BASE="https://repo1.maven.org/maven2/app/freerouting/freerouting/${VERSION}"
JAR="freerouting-${VERSION}-executable.jar"
DEST="$(cd "$(dirname "$0")/.." && pwd)/tools"

mkdir -p "$DEST"
curl -fsSL -o "$DEST/$JAR" "$BASE/$JAR"
expected="$(curl -fsSL "$BASE/$JAR.sha1" | awk '{print $1}')"
actual="$(sha1sum "$DEST/$JAR" 2>/dev/null | awk '{print $1}' || shasum "$DEST/$JAR" | awk '{print $1}')"
if [[ "$expected" != "$actual" ]]; then
  echo "SHA-1 mismatch for $JAR (expected $expected, got $actual)" >&2
  rm -f "$DEST/$JAR"
  exit 1
fi
mv "$DEST/$JAR" "$DEST/freerouting.jar"
echo "Freerouting $VERSION installed at $DEST/freerouting.jar"
