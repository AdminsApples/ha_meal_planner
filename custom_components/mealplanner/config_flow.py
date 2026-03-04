from __future__ import annotations
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_BASE_URL, CONF_SLOT, DEFAULT_SLOT


class MealPlannerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            schema = vol.Schema({
                vol.Required(CONF_BASE_URL, default="http://addon_mealplanner:8099"): str,
                vol.Required(CONF_SLOT, default=DEFAULT_SLOT): str,
            })
            return self.async_show_form(step_id="user", data_schema=schema)

        await self.async_set_unique_id("mealplanner_singleton")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title="Meal Planner", data=user_input)