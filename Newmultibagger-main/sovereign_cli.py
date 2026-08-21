"""Root-level shim — makes `import sovereign_cli` resolve to legacy.sovereign_cli."""
import sys
import legacy.sovereign_cli as _impl

sys.modules[__name__] = _impl
