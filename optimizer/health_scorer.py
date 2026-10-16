from typing import Any, Dict, List
from optimizer.slop_auditor import SlopAuditor
from optimizer.hotspot_scanner import HotspotScanner
from optimizer.dependency_auditor import DependencyAuditor


class HealthScorer:
    """
    Phase 4.3: Deterministic 0-100 Codebase Health Scorer.
    Aggregates telemetry across Phase 2 (Anti-AI-Slop), Phase 3 (Runtime Hotspots & Complexity),
    and Phase 4 (Dependency & File Hygiene) into a weighted 0-100 score and letter grade.
    """

    @staticmethod
    def _letter_grade(score: int) -> str:
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 85:
            return "B+"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"

    @classmethod
    def calculate_health(cls, root_dir: str = ".") -> Dict[str, Any]:
        """Runs all static analyzers and computes the weighted 0-100 health breakdown."""
        # Phase 2 metrics
        clones = SlopAuditor.find_duplicate_logic(root_dir)
        dead_exports_map = SlopAuditor.find_dead_exports(root_dir)
        dead_export_count = sum(len(v) for v in dead_exports_map.values())
        wrappers = SlopAuditor.find_useless_wrappers(root_dir)

        # Phase 3 metrics
        loop_hotspots = HotspotScanner.scan_loop_hotspots(root_dir)
        complexity_violations = HotspotScanner.check_complexity(root_dir)
        heavy_imports = HotspotScanner.find_heavy_imports(root_dir)

        # Phase 4 metrics
        dep_report = DependencyAuditor.audit_requirements(root_dir)
        ghost_deps = dep_report.get("potential_ghost_dependencies", [])
        undeclared_deps = dep_report.get("undeclared_third_party_imports", [])
        orphan_files = DependencyAuditor.find_orphan_files(root_dir)

        # 1. Anti-Slop & Modularity Subscore (Max 30 pts)
        slop_deductions = (len(clones) * 5) + (dead_export_count * 2) + (len(wrappers) * 3)
        slop_score = max(0, 30 - slop_deductions)

        # 2. Algorithmic & Runtime Efficiency Subscore (Max 25 pts)
        runtime_deductions = (len(loop_hotspots) * 5) + (len(heavy_imports) * 2)
        runtime_score = max(0, 25 - runtime_deductions)

        # 3. Structural Simplicity & Maintainability Subscore (Max 25 pts)
        complexity_deductions = len(complexity_violations) * 4
        complexity_score = max(0, 25 - complexity_deductions)

        # 4. Dependency & File Hygiene Subscore (Max 20 pts)
        hygiene_deductions = (len(ghost_deps) * 3) + (len(undeclared_deps) * 3) + (len(orphan_files) * 4)
        hygiene_score = max(0, 20 - hygiene_deductions)

        total_score = slop_score + runtime_score + complexity_score + hygiene_score
        grade = cls._letter_grade(total_score)

        # Build prioritized action items
        actions: List[str] = []
        for c in clones:
            locs = ", ".join(f"{l['file']}:{l['function']}" for l in c["locations"])
            actions.append(f"[HIGH | Clone] Consolidate duplicate AST logic ({locs}).")
        for h in loop_hotspots:
            actions.append(
                f"[HIGH | Hotspot] {h['file']}:{h['function']} (L{h['line']}) -> {h['recommendation']}"
            )
        for cv in complexity_violations[:5]:
            actions.append(
                f"[MED | Complexity] Refactor `{cv['file']}:{cv['function']}()` (L{cv['line']}): {', '.join(cv['reasons'])}."
            )
        for file, items in dead_exports_map.items():
            syms = ", ".join(i["symbol"] for i in items)
            actions.append(f"[MED | Dead Code] Remove unreferenced symbols in `{file}`: {syms}.")
        for w in wrappers:
            actions.append(
                f"[LOW | Wrapper] Inline hollow wrapper `{w['file']}:{w['wrapper_function']}()` -> `{w['delegates_directly_to']}()`."
            )
        if ghost_deps:
            actions.append(f"[LOW | Ghost Deps] Remove unused packages from manifest: {', '.join(ghost_deps)}.")
        if orphan_files:
            actions.append(f"[LOW | Orphan Files] Remove or wire up unreferenced modules: {', '.join(orphan_files)}.")

        return {
            "score": total_score,
            "grade": grade,
            "breakdown": {
                "anti_slop_and_modularity": f"{slop_score}/30",
                "runtime_efficiency": f"{runtime_score}/25",
                "maintainability_and_complexity": f"{complexity_score}/25",
                "dependency_and_file_hygiene": f"{hygiene_score}/20",
            },
            "counts": {
                "duplicate_ast_clones": len(clones),
                "dead_exports": dead_export_count,
                "hollow_wrappers": len(wrappers),
                "loop_io_hotspots": len(loop_hotspots),
                "complexity_violations": len(complexity_violations),
                "heavy_top_imports": len(heavy_imports),
                "ghost_dependencies": len(ghost_deps),
                "undeclared_imports": len(undeclared_deps),
                "orphan_files": len(orphan_files),
            },
            "prioritized_actions": actions,
        }

    @classmethod
    def format_health_report(cls, root_dir: str = ".") -> str:
        """Generates a clean executive Markdown scorecard for agents and developers."""
        data = cls.calculate_health(root_dir)
        b = data["breakdown"]
        c = data["counts"]

        lines = [
            f"# Codebase Health Scorecard: **{data['score']}/100** (Grade: **{data['grade']}**)",
            "",
            "## Category Breakdown",
            f"- **Anti-Slop & Modularity:** `{b['anti_slop_and_modularity']}` "
            f"*(Clones: {c['duplicate_ast_clones']}, Dead Symbols: {c['dead_exports']}, Wrappers: {c['hollow_wrappers']})*",
            f"- **Runtime Efficiency:** `{b['runtime_efficiency']}` "
            f"*(Loop I/O Hotspots: {c['loop_io_hotspots']}, Heavy Imports: {c['heavy_top_imports']})*",
            f"- **Maintainability & Complexity:** `{b['maintainability_and_complexity']}` "
            f"*(Complexity Violations: {c['complexity_violations']})*",
            f"- **Dependency & File Hygiene:** `{b['dependency_and_file_hygiene']}` "
            f"*(Ghost Deps: {c['ghost_dependencies']}, Orphan Files: {c['orphan_files']})*",
        ]

        lines.append("\n## Prioritized Remediation Checklist")
        if not data["prioritized_actions"]:
            lines.append("- **Zero issues found.** Codebase is in peak condition.")
        else:
            for idx, act in enumerate(data["prioritized_actions"], 1):
                lines.append(f"{idx}. {act}")

        return "\n".join(lines)
