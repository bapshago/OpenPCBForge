"""The agent's lookup tools, exercised without calling the API."""

import pytest

pytest.importorskip("anthropic")
from pcbforge import agent, env  # noqa: E402

needs_libs = pytest.mark.skipif(
    not (env.SYMBOL_DIR / "Device.kicad_sym").is_file(), reason="KiCad libraries not installed"
)


@needs_libs
def test_search_symbols_finds_led():
    assert "LED" in agent.search_symbols.call({"library": "Device", "pattern": "^LED$"}).splitlines()


@needs_libs
def test_symbol_pins():
    assert agent.symbol_pins.call({"library": "Device", "symbol": "LED"}).splitlines() == ["1: K", "2: A"]


@needs_libs
def test_search_footprints():
    assert "R_0805_2012Metric" in agent.search_footprints.call({"library": "Resistor_SMD", "pattern": "0805"})


def test_unknown_library_is_reported():
    assert "No symbol library" in agent.search_symbols.call({"library": "Nope", "pattern": "x"})


@pytest.mark.parametrize("name", ["../escape", "Upper", "1abc", ""])
def test_write_design_rejects_bad_names(name):
    assert "name must be" in agent.write_design.call({"name": name, "code": ""})
