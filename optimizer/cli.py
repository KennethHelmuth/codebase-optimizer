import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from optimizer.ast_engine import ASTSymbolEngine
from optimizer.slop_auditor import SlopAuditor
from optimizer.hotspot_scanner import HotspotScanner
from optimizer.dependency_auditor import DependencyAuditor
from optimizer.health_scorer import HealthScorer

console = Console()

@click.group()
def cli():
    """⚡ Codebase Optimizer CLI: Surgical AST context compression and anti-slop audit engine."""
    pass

@cli.command()
@click.argument("path", default=".")
def map(path: str):
    """Generate compact repository skeleton symbol map."""
    console.print(f"[bold cyan]Mapping repository skeleton for:[/bold cyan] {path}")
    result = ASTSymbolEngine.get_repo_map(path)
    console.print(result)

@cli.command()
@click.argument("file_path")
@click.option("--symbol", "-s", default=None, help="Target symbol (ClassName.method or function_name) to slice.")
def outline(file_path: str, symbol: str):
    """Extract file outline or targeted transitive symbol slice."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        console.print(f"[bold red]Error reading file {file_path}: {e}[/bold red]")
        sys.exit(1)

    if symbol:
        console.print(f"[bold cyan]Slicing symbol '{symbol}' from {file_path}...[/bold cyan]")
        res = ASTSymbolEngine.get_symbol_slice(code, symbol)
    else:
        console.print(f"[bold cyan]Extracting file outline for {file_path}...[/bold cyan]")
        res = ASTSymbolEngine.get_outline(code)
    console.print(res)

@cli.command()
@click.argument("path", default=".")
def slop(path: str):
    """Audit repository for AST clones, dead exports, and useless wrappers."""
    console.print(f"[bold yellow]Running Anti-AI-Slop audit on:[/bold yellow] {path}")
    report = SlopAuditor.format_slop_report(path)
    console.print(report)

@cli.command()
@click.argument("path", default=".")
def hotspots(path: str):
    """Scan runtime hotspots, complexity violations, and heavy imports."""
    console.print(f"[bold yellow]Scanning runtime bottlenecks and complexity on:[/bold yellow] {path}")
    report = HotspotScanner.format_hotspot_report(path)
    console.print(report)

@cli.command()
@click.argument("path", default=".")
def hygiene(path: str):
    """Audit dependencies and orphaned module files."""
    console.print(f"[bold cyan]Auditing dependency hygiene and orphan files on:[/bold cyan] {path}")
    dep_report = DependencyAuditor.audit_requirements(path)
    orphans = DependencyAuditor.find_orphan_files(path)

    console.print(Panel(f"Declared Packages: {len(dep_report.get('declared_packages', []))}\n"
                        f"Ghost Dependencies: {dep_report.get('potential_ghost_dependencies', [])}\n"
                        f"Undeclared Imports: {dep_report.get('undeclared_third_party_imports', [])}\n"
                        f"Orphan Files: {orphans}", title="Dependency & File Hygiene Audit", border_style="green"))

@cli.command()
@click.argument("path", default=".")
def score(path: str):
    """Compute deterministic 0-100 Codebase Health Scorecard & remediation checklist."""
    console.print(f"[bold magenta]Computing Codebase Health Scorecard for:[/bold magenta] {path}")
    report = HealthScorer.format_health_report(path)
    console.print(report)

if __name__ == "__main__":
    cli()
