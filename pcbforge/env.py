"""Locate KiCad's libraries and tools.

Import this before `skidl` so SKiDL can find the KiCad symbol libraries.
Every path can be overridden with an environment variable.
"""

import os
import platform
import shutil
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """KEY=VALUE lines from `path` into os.environ (blank lines and # comments skipped,
    optional quotes stripped). Variables already set in the environment win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        for prefix in ("export ", "set ", "SET "):      # bash or cmd style lines work too
            key = key.removeprefix(prefix).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key and value:
            os.environ.setdefault(key, value)


# The repo's .env (git-ignored) holds API keys and local overrides; see .env.example.
DOTENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(DOTENV)

_DEFAULT_SHARE = {
    "Linux": "/usr/share/kicad",
    "Darwin": "/Applications/KiCad/KiCad.app/Contents/SharedSupport",
    "Windows": r"C:\Program Files\KiCad\9.0\share\kicad",
}

KICAD_SHARE = Path(os.environ.get("KICAD_SHARE", _DEFAULT_SHARE.get(platform.system(), "/usr/share/kicad")))
SYMBOL_DIR = Path(os.environ.get("KICAD9_SYMBOL_DIR", KICAD_SHARE / "symbols"))
FOOTPRINT_DIR = Path(os.environ.get("KICAD9_FOOTPRINT_DIR", KICAD_SHARE / "footprints"))
KICAD_CLI = os.environ.get("KICAD_CLI", shutil.which("kicad-cli") or "kicad-cli")
# Freerouting 2.4+ needs Java 25+; point JAVA at that runtime if it is not first on PATH.
JAVA = os.environ.get("JAVA", "java")
SKIDL_TOOL = os.environ.get("SKIDL_TOOL", "KICAD9")
FREEROUTING_JAR = os.environ.get("FREEROUTING_JAR", str(Path(__file__).resolve().parent.parent / "tools" / "freerouting.jar"))
# Footprints adapted for the fab (footprints/README.md), found before KiCad's own libraries.
LOCAL_FOOTPRINT_DIR = Path(os.environ.get("PCBFORGE_FOOTPRINT_DIR", Path(__file__).resolve().parent.parent / "footprints"))


def footprint_lib_dir(lib: str) -> Path:
    """Folder of footprint library `lib`: the repo's own library if it has one by that name, else KiCad's."""
    local = LOCAL_FOOTPRINT_DIR / f"{lib}.pretty"
    return local if local.is_dir() else FOOTPRINT_DIR / f"{lib}.pretty"

# SKiDL reads these when it is imported.
os.environ.setdefault("KICAD9_SYMBOL_DIR", str(SYMBOL_DIR))
os.environ.setdefault("KICAD9_FOOTPRINT_DIR", str(FOOTPRINT_DIR))
