"""Compatibility shim — makes `modules.hybrid_scoring` resolve directly to `modules.scoring.ml_score`."""
import sys
import modules.scoring.ml_score as _impl

sys.modules[__name__] = _impl
