"""MOCK_OLT hardware model."""

from fncollect.vendors.mock import MockOLT, MockONTMock


class MOCK_OLT(MockOLT):
    """Deterministic OLT board for demos."""


class MOCK_ONT(MockONTMock):
    """Deterministic ONT for demos."""
