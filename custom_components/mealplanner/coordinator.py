from __future__ import annotations
import aiohttp
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_POLL_SECONDS


class MealPlannerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, base_url: str, slot: str):
        self.hass = hass
        self.base_url = base_url.rstrip("/")
        self.slot = slot

        super().__init__(
            hass,
            logger=None,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_POLL_SECONDS),
        )

    async def _fetch_json(self, session: aiohttp.ClientSession, path: str):
        url = f"{self.base_url}{path}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status >= 400:
                raise UpdateFailed(f"HTTP {resp.status} from {url}")
            return await resp.json()

    async def _async_update_data(self):
        try:
            async with aiohttp.ClientSession() as session:
                today = await self._fetch_json(session, f"/api/today?slot={self.slot}")
                tomorrow = await self._fetch_json(session, f"/api/tomorrow?slot={self.slot}")
            return {"today": today, "tomorrow": tomorrow}
        except Exception as err:
            raise UpdateFailed(str(err)) from err