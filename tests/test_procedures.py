"""Tests for the non-programmer UX: auto-regex + procedure catalog."""

from fncollect.processors import auto_regex, extract_values
from fncollect.vendors.isam import IsamVendor


def test_auto_regex_extracts_version():
    line = "    isam-feature-group : R6.6.02g"
    pattern = auto_regex(line, "6.6.02")
    assert pattern is not None
    values = extract_values(line, [{"name": "v", "regex": pattern}])
    assert values["v"] == "6.6.02"


def test_auto_regex_int():
    line = "slot count : 9"
    pattern = auto_regex(line, "9")
    assert pattern is not None
    assert extract_values(line, [{"name": "n", "regex": pattern}])["n"] == "9"


def test_auto_regex_with_suffix():
    # value is the tail of the line
    line = "mib-version : 3FE21961EAAA"
    pattern = auto_regex(line, "3FE21961EAAA")
    assert pattern is not None
    assert extract_values(line, [{"name": "m", "regex": pattern}])["m"] == "3FE21961EAAA"


def test_auto_regex_missing_value():
    assert auto_regex("hello world", "nope") is None


def test_procedure_catalog():
    vendor = IsamVendor()
    procedures = vendor.list_procedures()
    assert "probe" in procedures
    assert "ont_cutthrough_setup" in procedures
    dcp = vendor.load_procedure("probe")
    assert dcp is not None and dcp.steps
