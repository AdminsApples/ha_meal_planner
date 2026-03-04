from __future__ import annotations
import aiohttp

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    SERVICE_GENERATE_SHOPPING_LIST,
    ATTR_WEEKS,
    ATTR_CLEAR_FIRST,
    ATTR_START,
)


async def async_register_services(hass: HomeAssistant, entry):
    base_url = entry.data["base_url"].rstrip("/")

    async def handle_generate(call: ServiceCall):
        weeks = int(call.data.get(ATTR_WEEKS, 1))
        clear_first = bool(call.data.get(ATTR_CLEAR_FIRST, True))
        start = call.data.get(ATTR_START)

        if weeks not in (1, 2):
            raise HomeAssistantError("weeks must be 1 or 2")

        qs = f"?weeks={weeks}"
        if start:
            qs += f"&start={start}"

        url = f"{base_url}/api/shopping_list{qs}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status >= 400:
                    raise HomeAssistantError(f"MealPlanner API error HTTP {resp.status}")
                data = await resp.json()

        items = data.get("items", [])
        if clear_first:
            # Clears completed items only; HA doesn't provide "clear all" by default
            await hass.services.async_call("shopping_list", "clear_completed", {}, blocking=True)

        # Add as “qty unit name” or “qty × name” for count-like units
        for it in items:
            name = it["name"]
            qty = it["qty_display"]
            unit = it["unit"]
            if unit.lower() in ("count", "x", "pcs", "piece", "pieces"):
                line = f"{qty} × {name}"
            else:
                line = f"{qty} {unit} {name}"

            await hass.services.async_call(
                "shopping_list",
                "add_item",
                {"name": line},
                blocking=True
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_SHOPPING_LIST,
        handle_generate,
    )