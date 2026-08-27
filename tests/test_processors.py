"""Tests for the value-processor library and generic device methods."""


from fncollect.processors import extract_values, parse
from fncollect.vendors.mock import MockVendor

OUTPUT = (
    "isam-feature-group : R6.6.02g\n"
)
TABLE = (
    "slot       |actual-type|enabled\n"
    "-----------+-----------+-------\n"
    "acu:1/1     ngfc-f      no\n"
    "nt-a        fant-f      yes\n"
)


def test_regex_processor():
    assert parse(OUTPUT, {"parser": "regex", "regex": r"R(\d+\.\d+\.\d+)", "group": 1}) == "6.6.02"


def test_kv_processor():
    assert parse(OUTPUT, {"parser": "kv", "key": "isam-feature-group"}) == "R6.6.02g"


def test_grid_processor_count():
    assert parse(TABLE, {"parser": "grid", "kind": "count", "header_row": 0}) == 2


def test_extract_values_multiple():
    values = extract_values(
        OUTPUT,
        [
            {"name": "sw_version", "parser": "regex", "regex": r"R(\d+\.\d+\.\d+)", "group": 1},
            {"name": "count", "parser": "grid", "kind": "count"},
        ],
    )
    # grid has no table in OUTPUT -> count defaults to 0; sw_version must still work
    assert values["sw_version"] == "6.6.02"


def test_grid_cell():
    assert parse(
        TABLE,
        {"parser": "grid", "kind": "cell", "header_row": 0, "row": 1, "column": "actual-type"},
    ) == "fant-f"


async def test_device_get_values():
    vendor = MockVendor()
    device = vendor.create_device()
    await device.connect()
    values = await device.get_values(
        "show version",
        [{"name": "model", "parser": "regex", "regex": r"Model: (.+)", "group": 1}],
    )
    await device.disconnect()
    assert "mock-OLT-1000" in values.get("model")


async def test_device_configure():
    vendor = MockVendor()
    device = vendor.create_device()
    await device.connect()
    ok = await device.configure("show version")
    await device.disconnect()
    assert ok is True
