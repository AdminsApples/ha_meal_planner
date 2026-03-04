from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def _meal_state(payload: dict) -> str:
    meal = payload.get("meal")
    if not meal or not meal.get("meal_name"):
        return "None"
    return meal["meal_name"]


def _attrs(payload: dict) -> dict:
    meal = payload.get("meal") or {}
    return {
        "date": payload.get("date"),
        "slot": payload.get("slot"),
        "servings": meal.get("servings"),
        "notes": meal.get("notes"),
        "meal_id": meal.get("meal_id"),
    }


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MealPlannerTodaySensor(coordinator),
        MealPlannerTomorrowSensor(coordinator),
    ])


class MealPlannerTodaySensor(CoordinatorEntity, SensorEntity):
    _attr_name = "Meal Planner Today"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_today"

    @property
    def native_value(self):
        return _meal_state(self.coordinator.data.get("today", {}))

    @property
    def extra_state_attributes(self):
        return _attrs(self.coordinator.data.get("today", {}))


class MealPlannerTomorrowSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "Meal Planner Tomorrow"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_tomorrow"

    @property
    def native_value(self):
        return _meal_state(self.coordinator.data.get("tomorrow", {}))

    @property
    def extra_state_attributes(self):
        return _attrs(self.coordinator.data.get("tomorrow", {}))