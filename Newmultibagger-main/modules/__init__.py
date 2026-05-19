# Init for modules
# Programmatically maps and registers sub-packages to preserve backward compatibility

import sys
import importlib
import importlib.abc
import importlib.util

MODULE_MAPPING = {
    # Data Layer
    "data_service": "data_layer.data_service",
    "data_freshness": "data_layer.data_freshness",
    "data_utils": "data_layer.data_utils",
    "db_utils": "data_layer.db_utils",
    "dq_gates": "data_layer.dq_gates",
    "connections": "data_layer.connections",
    
    # Intelligence
    "llm_engine": "intelligence.llm_engine",
    "llm_validator": "intelligence.llm_validator",
    "news": "intelligence.news",
    "news_gate": "intelligence.news_gate",
    "news_sentiment": "intelligence.news_sentiment",
    "promoter_intel": "intelligence.promoter_intel",
    "insider": "intelligence.insider",
    
    # Risk (Note: 'risk' package itself is handled by modules/risk/__init__.py)
    "stress_test": "risk.stress_test",
    "stress_tester": "risk.stress_tester",
    "correlation": "risk.correlation",
    "regime_hmm": "risk.regime_hmm",
    "probability": "risk.probability",
    "slippage": "risk.slippage",
    
    # Portfolio
    "portfolio_optimizer": "portfolio.portfolio_optimizer",
    "allocation_hrp": "portfolio.allocation_hrp",
    "capital_efficiency": "portfolio.capital_efficiency",
    "capital_simulator": "portfolio.capital_simulator",
    "optimizer": "portfolio.optimizer",
    "execution": "portfolio.execution",
    "execution_analyzer": "portfolio.execution_analyzer",
    "exit_engine": "portfolio.exit_engine",
    "tax_efficiency": "portfolio.tax_efficiency",
    
    # Reporting (Note: 'reporting' package itself is handled by modules/reporting/__init__.py)
    "html_report": "reporting.html_report",
    "score_diagnostics": "reporting.score_diagnostics",
    
    # Tracking
    "tracker": "tracking.tracker",
    "alpha_tracker": "tracking.alpha_tracker",
    "drift_monitor": "tracking.drift_monitor",
    "thesis_monitor": "tracking.thesis_monitor",
    "research_memory": "tracking.research_memory",
}

class BackwardCompatLoader:
    def __init__(self, target_fullname):
        self.target_fullname = target_fullname

    def create_module(self, spec):
        # Dynamically import the real module and return it
        return importlib.import_module(self.target_fullname)

    def exec_module(self, module):
        # The module is already executed during import_module
        pass

class BackwardCompatFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("modules."):
            parts = fullname.split(".")
            if len(parts) == 2:
                old_name = parts[1]
                if old_name in MODULE_MAPPING:
                    new_rel = MODULE_MAPPING[old_name]
                    new_fullname = f"modules.{new_rel}"
                    try:
                        spec = importlib.util.find_spec(new_fullname)
                        if spec is not None:
                            # Create a custom spec that uses our loader to load the new module
                            return importlib.machinery.ModuleSpec(
                                name=fullname,
                                loader=BackwardCompatLoader(new_fullname),
                                is_package=False
                            )
                    except Exception:
                        pass
        return None

# Register the finder
sys.meta_path.insert(0, BackwardCompatFinder())

def __getattr__(name):
    if name in MODULE_MAPPING:
        new_rel = MODULE_MAPPING[name]
        return importlib.import_module(f"modules.{new_rel}")
    raise AttributeError(f"module 'modules' has no attribute '{name}'")
