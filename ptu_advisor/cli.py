"""PTU Advisor CLI - Command-line interface for PTU recommendations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ptu_advisor import __version__
from ptu_advisor.auth import get_azure_credential, validate_access
from ptu_advisor.config import AnalysisConfig
from ptu_advisor.metrics.collector import MetricsCollector
from ptu_advisor.analysis.engine import DecisionEngine
from ptu_advisor.visualization.charts import ChartGenerator
from ptu_advisor.report.generator import ReportGenerator
from ptu_advisor.demo import (
    DemoScenario,
    generate_demo_metrics,
    display_scenario_info,
    display_fetched_metrics,
    list_demo_scenarios,
)

app = typer.Typer(
    name="ptu-advisor",
    help="Automated PTU vs PAYG recommendation tool for Azure AI Foundry deployments.",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"PTU Advisor v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """PTU Advisor - Automated PTU vs PAYG recommendations for Azure AI Foundry."""
    pass


@app.command()
def analyze(
    resource_group: Annotated[
        str,
        typer.Option(
            "--resource-group",
            "-g",
            help="Azure resource group containing the Foundry workspace.",
        ),
    ],
    workspace: Annotated[
        str,
        typer.Option(
            "--workspace",
            "-w",
            help="Azure AI Foundry workspace name.",
        ),
    ],
    deployment: Annotated[
        Optional[str],
        typer.Option(
            "--deployment",
            "-d",
            help="Model deployment name to analyze. Omit for account-wide analysis.",
        ),
    ] = None,
    subscription: Annotated[
        Optional[str],
        typer.Option(
            "--subscription",
            "-s",
            help="Azure subscription ID. Uses default if not specified.",
        ),
    ] = None,
    days: Annotated[
        int,
        typer.Option(
            "--days",
            help="Number of days to analyze (lookback period).",
            min=1,
            max=90,
        ),
    ] = 14,
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output path for the HTML report. Defaults to ./outputs/",
        ),
    ] = None,
    business_hours_only: Annotated[
        bool,
        typer.Option(
            "--business-hours",
            help="Analyze only business hours (9 AM - 6 PM).",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            help="Enable verbose output for debugging.",
        ),
    ] = False,
    enable_llm: Annotated[
        bool,
        typer.Option(
            "--enable-llm",
            help="Enable LLM-powered analysis enrichment (requires API access or uses mock).",
        ),
    ] = False,
) -> None:
    """
    Analyze a Foundry deployment and generate PTU recommendation.

    Connects to Azure AI Foundry, fetches historical metrics, and produces
    an explainable recommendation: PTU Recommended, Borderline, or Not Recommended.

    Example:
        ptu-advisor analyze -g my-rg -w my-workspace -d gpt-4o-deployment --days 14
    """
    console.print(
        Panel.fit(
            f"[bold blue]PTU Advisor v{__version__}[/bold blue]\n"
            f"Analyzing deployment: [green]{deployment or 'all deployments'}[/green]",
            title="🔍 Analysis Starting",
        )
    )

    # Configuration
    config = AnalysisConfig(
        resource_group=resource_group,
        workspace=workspace,
        deployment=deployment or "",
        subscription_id=subscription,
        lookback_days=days,
        business_hours_only=business_hours_only,
        verbose=verbose,
        enable_llm=enable_llm,
    )

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Step 1: Authenticate
            task = progress.add_task("Authenticating with Azure...", total=None)
            credential = get_azure_credential()
            validate_access(credential, config)
            progress.update(task, description="✅ Authenticated with Azure")

            # Step 2: Collect metrics
            progress.update(task, description="Collecting metrics from Azure Monitor...")
            collector = MetricsCollector(credential, config)
            metrics = collector.collect()
            progress.update(
                task, description=f"✅ Collected {len(metrics.timestamps)} data points"
            )

            # Step 3: Analyze
            progress.update(task, description="Analyzing deployment patterns...")
            engine = DecisionEngine(config)
            result = engine.analyze(metrics)
            progress.update(task, description="✅ Analysis complete")

            # Step 4: Generate charts
            progress.update(task, description="Generating visualizations...")
            chart_gen = ChartGenerator(config)
            charts = chart_gen.generate(metrics, result)
            progress.update(task, description=f"✅ Generated {len(charts)} charts")

            # Step 4.5: LLM enrichment (optional)
            llm_analysis = None
            if config.enable_llm:
                progress.update(task, description="Generating AI-powered analysis...")
                from ptu_advisor.llm.explainer import PTUExplainer
                from ptu_advisor.llm.provider import LLMConfig
                llm_config = LLMConfig(provider=config.llm_provider)
                explainer = PTUExplainer(config=llm_config)
                llm_result = explainer.generate_main_analysis(metrics, result)
                llm_analysis = llm_result.content
                progress.update(task, description="✅ AI analysis generated")

            # Step 5: Generate report
            progress.update(task, description="Generating HTML report...")
            report_gen = ReportGenerator(config)
            report_path = report_gen.generate(
                metrics=metrics,
                result=result,
                charts=charts,
                output_path=output,
                llm_analysis=llm_analysis,
            )
            progress.update(task, description="✅ Report generated")

        # Final output
        _print_summary(result, report_path)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1)


def _print_summary(result: "AnalysisResult", report_path: Path) -> None:
    """Print the recommendation summary to console."""
    from ptu_advisor.analysis.engine import Recommendation

    # Color based on recommendation
    color_map = {
        Recommendation.PTU_RECOMMENDED: "green",
        Recommendation.BORDERLINE: "yellow",
        Recommendation.PTU_NOT_RECOMMENDED: "red",
    }
    emoji_map = {
        Recommendation.PTU_RECOMMENDED: "✅",
        Recommendation.BORDERLINE: "⚠️",
        Recommendation.PTU_NOT_RECOMMENDED: "❌",
    }

    color = color_map.get(result.recommendation, "white")
    emoji = emoji_map.get(result.recommendation, "")

    console.print()
    console.print(
        Panel(
            f"[bold {color}]{emoji} {result.recommendation.value.replace('_', ' ').upper()}[/bold {color}]\n\n"
            f"{result.summary}",
            title="📊 Recommendation",
            border_style=color,
        )
    )
    console.print()
    console.print(f"📄 Full report saved to: [link=file://{report_path}]{report_path}[/link]")
    console.print()


@app.command()
def list_deployments(
    resource_group: Annotated[
        str,
        typer.Option(
            "--resource-group",
            "-g",
            help="Azure resource group containing the Foundry workspace.",
        ),
    ],
    workspace: Annotated[
        str,
        typer.Option(
            "--workspace",
            "-w",
            help="Azure AI Foundry workspace name.",
        ),
    ],
    subscription: Annotated[
        Optional[str],
        typer.Option(
            "--subscription",
            "-s",
            help="Azure subscription ID. Uses default if not specified.",
        ),
    ] = None,
) -> None:
    """
    List all model deployments in a Foundry workspace.

    Use this to discover available deployments before running analysis.

    Example:
        ptu-advisor list-deployments -g my-rg -w my-workspace
    """
    from ptu_advisor.auth import get_azure_credential
    from ptu_advisor.metrics.collector import list_workspace_deployments

    console.print("[bold]Fetching deployments...[/bold]")

    try:
        credential = get_azure_credential()
        deployments = list_workspace_deployments(
            credential=credential,
            subscription_id=subscription,
            resource_group=resource_group,
            workspace=workspace,
        )

        if not deployments:
            console.print("[yellow]No deployments found in this workspace.[/yellow]")
            return

        console.print(f"\n[bold]Found {len(deployments)} deployment(s):[/bold]\n")
        for dep in deployments:
            console.print(f"  • [green]{dep.name}[/green] ({dep.model}) - {dep.sku_type}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def demo(
    scenario: Annotated[
        str,
        typer.Option(
            "--scenario",
            "-s",
            help="Demo scenario: 'ptu-recommended', 'ptu-not-recommended', or 'borderline'",
        ),
    ] = "ptu-recommended",
    days: Annotated[
        int,
        typer.Option(
            "--days",
            help="Number of days of simulated data.",
            min=7,
            max=30,
        ),
    ] = 14,
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output path for the HTML report.",
        ),
    ] = None,
    show_metrics: Annotated[
        bool,
        typer.Option(
            "--show-metrics",
            help="Display detailed fetched metrics before analysis.",
        ),
    ] = True,
    enable_llm: Annotated[
        bool,
        typer.Option(
            "--enable-llm",
            help="Enable LLM-powered analysis enrichment.",
        ),
    ] = False,
) -> None:
    """
    Run PTU Advisor with simulated demo data.

    This mode allows you to see how PTU Advisor works without connecting
    to a real Azure Foundry deployment. Perfect for demos and testing.

    Available scenarios:
    - ptu-recommended: Enterprise production chatbot with high utilization
    - ptu-not-recommended: Dev/test assistant with sporadic usage
    - borderline: E-commerce recommendations with mixed signals

    Example:
        ptu-advisor demo ptu-recommended
        ptu-advisor demo ptu-not-recommended --days 30
    """
    # Parse scenario
    try:
        scenario_enum = DemoScenario(scenario)
    except ValueError:
        console.print(f"[bold red]Error:[/bold red] Unknown scenario '{scenario}'")
        console.print("\nAvailable scenarios:")
        list_demo_scenarios()
        raise typer.Exit(code=1)
    
    console.print()
    console.print(
        Panel.fit(
            f"[bold blue]PTU Advisor v{__version__}[/bold blue] - [yellow]DEMO MODE[/yellow]\n"
            f"Running scenario: [green]{scenario}[/green]",
            title="🎭 Demo Mode",
        )
    )
    
    # Display scenario info
    from ptu_advisor.demo import SCENARIOS
    scenario_config = SCENARIOS[scenario_enum]
    display_scenario_info(scenario_config)
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Step 1: Generate demo metrics
            task = progress.add_task("Generating simulated metrics...", total=None)
            metrics, config = generate_demo_metrics(scenario_enum, days)
            progress.update(
                task, 
                description=f"✅ Generated {len(metrics.timestamps)} data points over {days} days"
            )
        
        # Display fetched metrics if requested
        if show_metrics:
            display_fetched_metrics(metrics, config)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Step 2: Analyze
            task = progress.add_task("Analyzing deployment patterns...", total=None)
            analysis_config = AnalysisConfig(
                resource_group="demo-rg",
                workspace="demo-workspace",
                deployment=config.deployment_name,
                lookback_days=days,
            )
            engine = DecisionEngine(analysis_config)
            result = engine.analyze(metrics)
            progress.update(task, description="✅ Analysis complete")
            
            # Step 3: Generate charts
            progress.update(task, description="Generating visualizations...")
            chart_gen = ChartGenerator(analysis_config)
            charts = chart_gen.generate(metrics, result)
            progress.update(task, description=f"✅ Generated {len(charts)} charts")
            
            # Step 3.5: LLM enrichment (optional)
            llm_analysis = None
            if enable_llm:
                progress.update(task, description="Generating AI-powered analysis...")
                from ptu_advisor.llm.explainer import PTUExplainer
                from ptu_advisor.llm.provider import LLMConfig
                llm_config = LLMConfig(provider="mock")
                explainer_llm = PTUExplainer(config=llm_config)
                llm_result = explainer_llm.generate_main_analysis(metrics, result)
                llm_analysis = llm_result.content
                progress.update(task, description="✅ AI analysis generated")

            # Step 4: Generate report
            progress.update(task, description="Generating HTML report...")
            report_gen = ReportGenerator(analysis_config)
            report_path = report_gen.generate(
                metrics=metrics,
                result=result,
                charts=charts,
                output_path=output,
                llm_analysis=llm_analysis,
            )
            progress.update(task, description="✅ Report generated")
        
        # Final output
        _print_summary(result, report_path)
        
        # Demo mode notice
        console.print(
            Panel(
                "[yellow]This was a demo run with simulated data.[/yellow]\n"
                "To analyze a real deployment, use:\n\n"
                "[dim]ptu-advisor analyze -g <resource-group> -w <workspace> -d <deployment>[/dim]",
                title="ℹ️ Demo Mode",
                border_style="yellow",
            )
        )
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print_exception()
        raise typer.Exit(code=1)


@app.command(name="demo-list")
def demo_list() -> None:
    """
    List available demo scenarios.

    Example:
        ptu-advisor demo-list
    """
    console.print()
    console.print(
        Panel.fit(
            f"[bold blue]PTU Advisor v{__version__}[/bold blue] - Demo Scenarios",
            title="🎭 Available Demos",
        )
    )
    list_demo_scenarios()
    
    console.print("Run a demo with: [cyan]ptu-advisor demo <scenario-name>[/cyan]")
    console.print()


if __name__ == "__main__":
    app()
