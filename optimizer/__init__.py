"""Codebase Optimizer package."""
from optimizer.ast_engine import ASTSymbolEngine
from optimizer.context_pruner import ContextPruner
from optimizer.slop_auditor import SlopAuditor
from optimizer.hotspot_scanner import HotspotScanner
from optimizer.dead_code import DeadCodeAuditor
from optimizer.dependency_auditor import DependencyAuditor

__all__ = [
    "ASTSymbolEngine",
    "ContextPruner",
    "SlopAuditor",
    "HotspotScanner",
    "DeadCodeAuditor",
    "DependencyAuditor",
]
