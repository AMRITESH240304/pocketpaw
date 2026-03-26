# Pocket generation tool — creates a pocket workspace from AI-gathered research.
# The agent calls this after using web_search/browser to gather information.

import json
import logging
from typing import Any

from pocketpaw.tools.protocol import BaseTool

logger = logging.getLogger(__name__)


class CreatePocketTool(BaseTool):
    """Create a pocket workspace with widgets from research data.

    The agent calls this tool after gathering information via web_search,
    browser, or other research tools. The tool returns the pocket spec
    as JSON that the frontend can render via Ripple.
    """

    @property
    def name(self) -> str:
        return "create_pocket"

    @property
    def description(self) -> str:
        return (
            "Create a pocket workspace with widgets. Call this after researching a topic. "
            "Provide a name, description, category, and a list of widgets. "
            "Each widget has a name, display type, and data. "
            "\n\nDisplay types:\n"
            "- stats: key-value pairs. "
            "Data: {stats: [{label, value, trend?}]}\n"
            "- chart: bar/line/area/pie chart. "
            "Data: {bars: [{label, value, color?}], "
            "chartType?: 'bar'|'line'|'area'|'pie'}\n"
            "- table: data table with rows. "
            "Data: {headers: [str], "
            "rows: [{cells: [str], status?: '#hex'}]}\n"
            "- feed: activity/event feed. "
            "Data: {feedItems: [{text, time?, "
            "type?: 'success'|'warning'|'error'|'info'}]}\n"
            "- metric: single KPI with trend. "
            "Data: {metric: {label, value, trend?, description?}}\n"
            "- terminal: log/command output. "
            "Data: {termLines: [{text, "
            "type?: 'stdout'|'stderr'|'command', timestamp?}], "
            "termTitle?}\n"
            "\nFor complex layouts, use 'raw' type with a "
            "full Ripple UISpec in the 'spec' field.\n"
            "\nWidget colors: use hex colors like "
            "#30D158 (green), #FF453A (red), #FF9F0A (orange), "
            "#0A84FF (blue), #BF5AF2 (purple), #5E5CE6 (indigo), "
            "#FEBC2E (gold), #64D2FF (cyan).\n"
            "\nWidget span: 'col-span-1' (normal), "
            "'col-span-2' (wide), 'col-span-3' (full width)."
        )

    @property
    def trust_level(self) -> str:
        return "standard"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Pocket name (e.g. 'Vercel Analysis')",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the pocket's purpose",
                },
                "category": {
                    "type": "string",
                    "description": "Category: research, business, data, mission, deep-work, custom",
                    "enum": [
                        "research",
                        "business",
                        "data",
                        "mission",
                        "deep-work",
                        "custom",
                        "hospitality",
                    ],
                },
                "color": {
                    "type": "string",
                    "description": "Accent color for the pocket (hex, e.g. '#0A84FF')",
                },
                "widgets": {
                    "type": "array",
                    "description": "List of widgets to include in the pocket",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Widget name (e.g. 'Company Overview')",
                            },
                            "color": {
                                "type": "string",
                                "description": "Widget accent color (hex)",
                            },
                            "span": {
                                "type": "string",
                                "description": "Grid span: col-span-1, col-span-2, or col-span-3",
                                "enum": ["col-span-1", "col-span-2", "col-span-3"],
                            },
                            "display": {
                                "type": "object",
                                "description": "Widget display data. Must include 'type' field.",
                            },
                        },
                        "required": ["name", "display"],
                    },
                },
            },
            "required": ["name", "description", "category", "widgets"],
        }

    async def execute(
        self,
        name: str,
        description: str,
        category: str,
        widgets: list[dict[str, Any]],
        color: str = "#0A84FF",
        **kwargs: Any,
    ) -> str:
        """Build and return the pocket spec as JSON."""
        import uuid

        pocket_id = f"ai-{uuid.uuid4().hex[:8]}"

        # Build widget list with IDs
        built_widgets = []
        for i, w in enumerate(widgets):
            widget = {
                "id": f"{pocket_id}-w{i}",
                "name": w.get("name", f"Widget {i + 1}"),
                "color": w.get("color", color),
                "span": w.get("span", "col-span-1"),
                "display": w.get(
                    "display", {"type": "stats", "stats": [{"label": "Status", "value": "Ready"}]}
                ),
            }
            built_widgets.append(widget)

        pocket_spec = {
            "id": pocket_id,
            "name": name,
            "description": description,
            "type": category,
            "color": color,
            "widgets": built_widgets,
        }

        result_json = json.dumps(pocket_spec, indent=2)

        # Use a marker so the frontend can detect this is a pocket spec
        marker = f"<!-- pocket-spec:{result_json}:pocket-spec -->"
        msg = f"Created pocket **{name}** with {len(built_widgets)} widgets."
        return f"{marker}\n\n{msg}"
