import modules.adapters.yf_patch  # noqa: F401

"""Compatibility shim for legacy top-level imports."""

import sys  # noqa: E402

from scripts.internal import report_generator as _report_generator  # noqa: E402

sys.modules[__name__] = _report_generator
