import os
import sqlite3
from contextlib import contextmanager
from datetime import date

DB_PATH = os.environ.get("MEALPLANNER_DB_PATH", "/data/mealplanner.db")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@contextmanager
def get_db():
    con = _connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(default_slots: list[str]) -> None:
    with get_db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            notes TEXT DEFAULT ''
        );
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL DEFAULT 'count',
            rounding TEXT NOT NULL DEFAULT 'none'   -- none | ceil_int | ceil_step:<n> | round_step:<n>
        );
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS meal_ingredients (
            meal_id INTEGER NOT NULL,
            ingredient_id INTEGER NOT NULL,
            amount_per_person REAL NOT NULL,
            PRIMARY KEY(meal_id, ingredient_id),
            FOREIGN KEY(meal_id) REFERENCES meals(id) ON DELETE CASCADE,
            FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE
        );
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS plan (
            day TEXT NOT NULL,         -- YYYY-MM-DD
            slot TEXT NOT NULL,        -- breakfast/lunch/dinner etc
            meal_id INTEGER,
            servings INTEGER NOT NULL DEFAULT 2,
            PRIMARY KEY(day, slot),
            FOREIGN KEY(meal_id) REFERENCES meals(id) ON DELETE SET NULL
        );
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)

        # store default slots (simple)
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                    ("default_slots", ",".join(default_slots)))


def get_default_slots() -> list[str]:
    with get_db() as con:
        row = con.execute("SELECT value FROM settings WHERE key='default_slots'").fetchone()
        if not row:
            return ["breakfast", "lunch", "dinner"]
        return [s.strip() for s in row["value"].split(",") if s.strip()]


def ensure_plan_rows_for_week(start: date, days: int) -> None:
    slots = get_default_slots()
    with get_db() as con:
        for i in range(days):
            d = start.toordinal() + i
            day = date.fromordinal(d).isoformat()
            for slot in slots:
                con.execute("""
                INSERT OR IGNORE INTO plan(day, slot, meal_id, servings) VALUES(?,?,NULL,2)
                """, (day, slot))