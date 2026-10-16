import re
from typing import List
from optimizer.ast_engine import ASTSymbolEngine


class ContextPruner:
    """
    Phase 1.4: Diff Context Compressor & Token Budget Enforcer.
    Strips noise from Git diffs and enforces token ceilings on large context payloads.
    """

    @classmethod
    def compress_git_diff(cls, raw_diff: str) -> str:
        """
        Compresses a unified git diff by removing lockfiles, binary diffs,
        and excessive unchanged context lines while preserving file headers and hunks.
        """
        if not raw_diff.strip():
            return "# Empty diff."

        skip_patterns = (
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "poetry.lock", "Cargo.lock", ".min.js", ".min.css", ".svg"
        )

        compressed_Blocks: List[str] = []
        current_file = ""
        skip_current = False

        for line in raw_diff.splitlines():
            if line.startswith("diff --git"):
                skip_current = any(pat in line for pat in skip_patterns)
                if skip_current:
                    compressed_Blocks.append(f"# [Skipped noise/lockfile diff: {line}]")
                else:
                    compressed_Blocks.append(line)
                continue

            if skip_current:
                continue

            # Keep file headers, hunk markers, and actual additions/deletions
            if line.startswith(("+++", "---", "@@", "+", "-")):
                compressed_Blocks.append(line)
            elif line.startswith(" "):
                # Keep short context lines, trim long unchanged boilerplate lines
                if len(line) <= 100:
                    compressed_Blocks.append(line)

        result = "\n".join(compressed_Blocks)
        return ASTSymbolEngine.compression_stats(raw_diff, result) + "\n\n" + result
