"""Compatibility shim for legacy top-level imports."""

import sys

from scripts.internal import report_generator as _report_generator

sys.modules[__name__] = _report_generator
