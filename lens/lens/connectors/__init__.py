"""Connector pipeline: Transport -> raw_records -> typed core rows."""

from .base import SyncReport, SyncRunner

__all__ = ["SyncReport", "SyncRunner"]
