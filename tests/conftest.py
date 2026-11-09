# Set the KiCad library paths before any test imports SKiDL directly (pytest.importorskip("skidl")):
# SKiDL reads them once, at import, and a design built afterwards can't find its symbol libraries.
from pcbforge import env  # noqa: F401
