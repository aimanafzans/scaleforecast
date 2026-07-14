"""
Option 4: View Forecast Reports.

Two-step flow: pick a report from the numbered list, then pick an action:
view full details, category summary, at-risk SKUs (paginated), restock
recommendations (paginated), or delete the report.  Paginated views use
:func:`scaleforecast.cli.components.paginate_table`.
"""

from __future__ import annotations

import os

import pandas as pd
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from scaleforecast.cli.console import console
from scaleforecast.cli.components import (
    paginate_table, render_reports_table, render_section_header,
)
from scaleforecast.cli.controllers.base import BackToMenu
from scaleforecast.cli.session import SessionState
from scaleforecast.report_generator import (
    at_risk_skus, category_summary, delete_report, list_reports,
    restock_recommendations,
)


def run(session: SessionState) -> None:
    """Drive the Option 4 (View Forecast Reports) sub-flow."""
    render_section_header("View Forecast Reports")

    reports = list_reports()
    if not reports:
        console.print("[warn]No forecast reports found. "
                       "Run a forecast first (Option 3).[/warn]")
        console.print()
        input("Press Enter to return to the main menu...")
        return

    while True:
        # Refresh the list each iteration so deletions are reflected.
        reports = list_reports()
        if not reports:
            console.print("[muted_line]All reports deleted — returning to menu.[/muted_line]")
            console.print()
            input("Press Enter to continue...")
            return
        render_reports_table(reports)
        console.print()
        console.print(
            "  Enter the [accent]#[/accent] of a report to inspect, "
            "or [muted_line]B[/muted_line] to go back."
        )
        choice = Prompt.ask("[prompt]Select a report[/prompt]", default="B")
        if choice.strip().upper() in ("B", "BACK", "Q", "QUIT"):
            return
        try:
            idx = int(choice) - 1
        except ValueError:
            console.print("[bad]Invalid input. Please enter a number or B.[/bad]")
            continue
        if not (0 <= idx < len(reports)):
            console.print(f"[bad]Invalid number. Pick 1–{len(reports)}.[/bad]")
            continue
        rpt = reports[idx]
        try:
            _show_report_actions(rpt)
        except BackToMenu:
            continue


def _show_report_actions(rpt) -> None:
    """
    Show the numbered actions sub-menu for the user-selected *rpt*.

    Raises :class:`BackToMenu` when the user types B at any prompt in this
    sub-flow, returning the outer loop to the report list.
    """
    df = pd.read_csv(rpt.filepath)
    results = df.to_dict("records")

    while True:
        console.print()
        console.print(f"[heading]Viewing: {rpt.filename}[/heading]")
        console.print(f"    Source dataset:  {rpt.source_dataset}")
        console.print(f"    Technique:       {rpt.technique}")
        console.print(f"    SKUs:            {rpt.sku_count:,}")
        console.print(f"    At-risk count:   {rpt.at_risk_count:,}")
        console.print()
        console.print("  [bold accent]1.  View full report details[/bold accent]")
        console.print("  [bold accent]2.  View category-level summary[/bold accent]")
        console.print("  [bold accent]3.  View at-risk SKUs[/bold accent] (paginated)")
        console.print("  [bold accent]4.  View restock recommendations[/bold accent] (paginated)")
        console.print("  [bold accent]5.  Delete this report[/bold accent]")
        console.print("  [muted_line]B.  Back to report list[/muted_line]")

        action = Prompt.ask("[prompt]Select an action[/prompt]", default="B")
        action = action.strip().upper()
        if action in ("B", "BACK", "Q", "QUIT"):
            raise BackToMenu()
        if action == "1":
            _action_view_full(rpt, results)
        elif action == "2":
            _action_category_summary(results)
        elif action == "3":
            _action_at_risk(results)
        elif action == "4":
            _action_restock(results)
        elif action == "5":
            _action_delete(rpt)
            return  # After delete, return to report list (which will refresh).
        else:
            console.print("[bad]Unknown action. Pick 1–5 or B.[/bad]")


def _action_view_full(rpt, results) -> None:
    """Show the combined view details: at-risk SKUs (top-N) + restock (top-N)."""
    # For "full" view, we keep a quick top-20 scroll view rather than
    # paginating both lists, since the per-list paging views (3 / 4) are
    # available as dedicated sub-actions.
    at_risk = at_risk_skus(results)
    if at_risk:
        console.print()
        console.print("[heading]At-Risk SKUs (top 20; use action 3 to page through all)[/heading]")
        risk_table = Table()
        risk_table.add_column("SKU ID", style="info")
        risk_table.add_column("Category")
        risk_table.add_column("Stock", justify="right")
        risk_table.add_column("Reorder Pt", justify="right")
        risk_table.add_column("Risk", style="bad")
        risk_table.add_column("Rec. Qty", justify="right")
        for sku in at_risk[:20]:
            risk_table.add_row(
                sku.get("sku_id", ""),
                sku.get("category", ""),
                str(sku.get("current_stock", "")),
                str(sku.get("reorder_point", "")),
                str(sku.get("stockout_risk", "")),
                str(sku.get("recommended_order_qty", "")),
            )
        console.print(risk_table)
        if len(at_risk) > 20:
            console.print(
                f"  [muted_line]... and {len(at_risk) - 20} more. "
                f"Use action 3 to page through them all.[/muted_line]"
            )
    else:
        console.print("[ok]No SKUs at risk of stockout.[/ok]")

    restock = restock_recommendations(results)
    if restock:
        console.print()
        console.print(f"[heading]Restock Recommendations (top 10; use action 4 for all)[/heading]")
        refill_table = Table()
        refill_table.add_column("SKU ID", style="info")
        refill_table.add_column("Stock", justify="right")
        refill_table.add_column("Reorder Pt", justify="right")
        refill_table.add_column("Order Qty", justify="right")
        for sku in restock[:10]:
            refill_table.add_row(
                sku.get("sku_id", ""),
                str(sku.get("current_stock", "")),
                str(sku.get("reorder_point", "")),
                str(sku.get("recommended_order_qty", "")),
            )
        console.print(refill_table)
        if len(restock) > 10:
            console.print(
                f"  [muted_line]... and {len(restock) - 10} more. "
                f"Use action 4 to page through them all.[/muted_line]"
            )


def _action_category_summary(results) -> None:
    summary = category_summary(results)
    if not summary:
        console.print("[warn]No category data available.[/warn]")
        return
    console.print()
    console.print("[heading]Category-Level Demand Trend Summary[/heading]")
    cat_table = Table()
    for col in summary[0].keys():
        cat_table.add_column(str(col).replace("_", " ").title(), style="info")
    for row in summary:
        cat_table.add_row(*[str(v) for v in row.values()])
    console.print(cat_table)


def _action_at_risk(results) -> None:
    at_risk = at_risk_skus(results)
    if not at_risk:
        console.print("[ok]No SKUs at risk of stockout.[/ok]")
        return

    console.print()
    console.print(f"[heading]At-Risk SKUs ({len(at_risk)} total)[/heading]")
    template = Table(title="At-Risk SKUs")
    template.add_column("SKU ID", style="info")
    template.add_column("Category")
    template.add_column("Stock", justify="right")
    template.add_column("Reorder Pt", justify="right")
    template.add_column("Risk", style="bad")
    template.add_column("Rec. Qty", justify="right")

    rows = [
        (
            sku.get("sku_id", ""),
            sku.get("category", ""),
            str(sku.get("current_stock", "")),
            str(sku.get("reorder_point", "")),
            str(sku.get("stockout_risk", "")),
            str(sku.get("recommended_order_qty", "")),
        )
        for sku in at_risk
    ]
    paginate_table(template, rows, page_size=50,
                   prompt_label="At-risk list navigation")


def _action_restock(results) -> None:
    restock = restock_recommendations(results)
    if not restock:
        console.print("[ok]No restock recommendations -- inventory looks healthy.[/ok]")
        return

    console.print()
    console.print(f"[heading]Restock Recommendations ({len(restock)} SKUs)[/heading]")
    template = Table(title="Restock Recommendations")
    template.add_column("SKU ID", style="info")
    template.add_column("Stock", justify="right")
    template.add_column("Reorder Pt", justify="right")
    template.add_column("Order Qty", justify="right")

    rows = [
        (
            sku.get("sku_id", ""),
            str(sku.get("current_stock", "")),
            str(sku.get("reorder_point", "")),
            str(sku.get("recommended_order_qty", "")),
        )
        for sku in restock
    ]
    paginate_table(template, rows, page_size=50,
                   prompt_label="Restock list navigation")


def _action_delete(rpt) -> None:
    if Confirm.ask(f"[bad]Delete '{rpt.filename}'?[/bad]", default=False):
        success, msg = delete_report(rpt.filename)
        console.print(f"[ok]{msg}[/ok]" if success else f"[bad]{msg}[/bad]")


__all__ = ["run"]