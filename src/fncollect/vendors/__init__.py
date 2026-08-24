"""Vendor packs shipped with fncollect."""

from fncollect.vendors.mock import MockVendor
from fncollect.vendors.registry import registry

registry.register(MockVendor)
