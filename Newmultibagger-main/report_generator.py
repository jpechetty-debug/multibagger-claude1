"""Root-level shim — makes `import report_generator` resolve to legacy.report_generator."""
import sys
import legacy.report_generator as _impl

sys.modules[__name__] = _impl
