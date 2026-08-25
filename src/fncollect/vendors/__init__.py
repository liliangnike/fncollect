"""Vendor packs shipped with fncollect.

Importing this package and calling ``discover_vendors`` (see
``fncollect.vendors.registry``) registers every available vendor.
"""

from fncollect.vendors.registry import discover_vendors, registry

__all__ = ["discover_vendors", "registry"]
