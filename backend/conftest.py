"""Fail before collection/imports, not in a fixture after SessionLocal exists."""
import pytest
from test_database_guard import bootstrap, UnsafeTestDatabase

try:
    bootstrap()
except UnsafeTestDatabase as error:
    raise pytest.UsageError(str(error)) from None