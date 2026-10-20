from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from prolifik_api.items import brand_item
from prolifik_api.tooling import client_for, emit

VARIABLES = ("active_brand_id", "brands")


class ListBrandsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        data = client_for(self).get("/brands")
        active = data.get("activeBrandId") if isinstance(data.get("activeBrandId"), str) else None
        brands = [brand_item(brand, active) for brand in data.get("brands") or [] if isinstance(brand, dict)]
        result = {"active_brand_id": active, "brands": brands}

        if not brands:
            text = "This Prolifik account has no brands yet. Add one at https://app.getprolifik.com."
        else:
            lines = [f"{len(brands)} brand{'s' if len(brands) != 1 else ''}:"]
            for brand in brands:
                notes = []
                if brand["is_active_brand"]:
                    notes.append("active")
                if not brand["usable_on_plan"]:
                    notes.append("locked on current plan")
                suffix = f" ({', '.join(notes)})" if notes else ""
                lines.append(f"- {brand['name'] or 'Untitled'}: {brand['id']}{suffix}")
            text = "\n".join(lines)
        yield from emit(self, result, text, VARIABLES)
