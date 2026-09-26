"""Tests for AI Harness Textual Application."""

import pytest
from textual.widgets import TabbedContent, Button, DataTable, RichLog

from odin.textual_app import AIHarnessTextualApp


@pytest.mark.asyncio
async def test_textual_app_lifecycle():
    """Verify Textual app initializes, mounts widgets, and registers key tabs."""
    app = AIHarnessTextualApp()
    async with app.run_test() as pilot:
        assert app.is_running
        
        # Verify primary widgets
        tabs = app.query_one("#tabs", TabbedContent)
        assert tabs is not None
        
        btn_bench = app.query_one("#btn-overview-benchmark", Button)
        assert btn_bench is not None
        
        table_patches = app.query_one("#table-patches", DataTable)
        assert table_patches is not None
        
        table_errors = app.query_one("#table-errors", DataTable)
        assert table_errors is not None
        
        log = app.query_one("#overview-log", RichLog)
        assert log is not None


@pytest.mark.asyncio
async def test_textual_app_tab_switch_actions():
    """Verify switching tabs via actions."""
    app = AIHarnessTextualApp()
    async with app.run_test() as pilot:
        tabs = app.query_one("#tabs", TabbedContent)
        
        app.action_switch_tab("tab-solver")
        assert tabs.active == "tab-solver"
        
        app.action_switch_tab("tab-patches")
        assert tabs.active == "tab-patches"
        
        app.action_switch_tab("tab-errors")
        assert tabs.active == "tab-errors"
