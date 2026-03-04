import os
import math
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from db import init_db, get_db, get_default_slots, ensure_plan_rows_for_week

app = FastAPI(title="Meal Planner")
templates = Jinja2Templates(directory="templates")


def ingress_base(request: Request) -> str:
    """
    Home Assistant Ingress puts the proxy prefix in headers.
    We MUST use this for links + redirects, otherwise clicks go to HA and 404.
    """
    p = (
        request.headers.get("X-Ingress-Path")
        or request.headers.get("X-Forwarded-Prefix")
        or os.environ.get("MEALPLANNER_INGRESS_PATH", "")
    )
    return (p or "").rstrip("/")


def _round_qty(qty: float, rounding: str) -> float:
    if rounding == "none":
        return qty
    if rounding == "ceil_int":
        return float(math.ceil(qty))
    if rounding.startswith("ceil_step:"):
        step = float(rounding.split(":", 1)[1])
        return float(math.ceil(qty / step) * step)
    if rounding.startswith("round_step:"):
        step = float(rounding.split(":", 1)[1])
        return float(round(qty / step) * step)
    return qty


def _fmt_qty(qty: float) -> str:
    # Make 2.0 show as 2
    if abs(qty - int(qty)) < 1e-9:
        return str(int(qty))
    return f"{qty:.2f}".rstrip("0").rstrip(".")


@app.on_event("startup")
def startup():
    # idempotent
    init_db(default_slots=["breakfast", "lunch", "dinner"])


# --------------------
# UI
# --------------------
@app.get("/", response_class=HTMLResponse)
def ui_home(request: Request):
    base = ingress_base(request)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "ingress": base},
    )


# --------------------
# Meals UI
# --------------------
@app.get("/meals", response_class=HTMLResponse)
def ui_meals(request: Request, meal_id: Optional[int] = None):
    """
    Shows meals + ingredients and (optionally) an ingredient editor for the selected meal.
    """
    base = ingress_base(request)

    with get_db() as con:
        meals = con.execute("SELECT * FROM meals ORDER BY name").fetchall()
        ingredients = con.execute("SELECT * FROM ingredients ORDER BY name").fetchall()

        selected_meal = None
        ingredient_amounts: dict[int, float] = {}

        if meal_id:
            selected_meal = con.execute("SELECT * FROM meals WHERE id=?", (meal_id,)).fetchone()
            rows = con.execute(
                """
                SELECT ingredient_id, amount_per_person
                FROM meal_ingredients
                WHERE meal_id=?
                """,
                (meal_id,),
            ).fetchall()
            ingredient_amounts = {int(r["ingredient_id"]): float(r["amount_per_person"]) for r in rows}

    return templates.TemplateResponse(
        "meals.html",
        {
            "request": request,
            "ingress": base,
            "meals": meals,
            "ingredients": ingredients,
            "selected_meal": selected_meal,
            "ingredient_amounts": ingredient_amounts,
        },
    )


@app.post("/meals/add")
def ui_meals_add(
    request: Request,
    name: str = Form(...),
    notes: str = Form(""),
):
    with get_db() as con:
        con.execute(
            "INSERT OR IGNORE INTO meals(name, notes) VALUES(?,?)",
            (name.strip(), notes.strip()),
        )
    base = ingress_base(request)
    return RedirectResponse(url=f"{base}/meals", status_code=303)


@app.post("/ingredients/add")
def ui_ingredients_add(
    request: Request,
    name: str = Form(...),
    unit: str = Form("count"),
    rounding: str = Form("none"),
):
    with get_db() as con:
        con.execute(
            "INSERT OR IGNORE INTO ingredients(name, unit, rounding) VALUES(?,?,?)",
            (name.strip(), unit.strip(), rounding.strip()),
        )
    base = ingress_base(request)
    return RedirectResponse(url=f"{base}/meals", status_code=303)


@app.post("/meal_ingredients/save")
async def ui_meal_ingredients_save(request: Request):
    """
    Save ALL ingredient amounts for a meal in one go.
    Form fields: meal_id, amount_<ingredientId>=<float or blank>
    - blank deletes the ingredient from the meal
    - number upserts it
    """
    base = ingress_base(request)
    form = await request.form()

    meal_id_raw = form.get("meal_id")
    if not meal_id_raw:
        return RedirectResponse(url=f"{base}/meals", status_code=303)

    meal_id = int(meal_id_raw)

    updates: list[tuple[int, float]] = []
    deletes: list[int] = []

    for key, val in form.items():
        if not key.startswith("amount_"):
            continue
        ing_id = int(key.split("_", 1)[1])
        v = (val or "").strip()

        if v == "":
            deletes.append(ing_id)
        else:
            try:
                amt = float(v)
                updates.append((ing_id, amt))
            except ValueError:
                # ignore invalid
                pass

    with get_db() as con:
        for ing_id in deletes:
            con.execute(
                "DELETE FROM meal_ingredients WHERE meal_id=? AND ingredient_id=?",
                (meal_id, ing_id),
            )

        for ing_id, amt in updates:
            con.execute(
                """
                INSERT INTO meal_ingredients(meal_id, ingredient_id, amount_per_person)
                VALUES(?,?,?)
                ON CONFLICT(meal_id, ingredient_id)
                DO UPDATE SET amount_per_person=excluded.amount_per_person
                """,
                (meal_id, ing_id, amt),
            )

    return RedirectResponse(url=f"{base}/meals?meal_id={meal_id}", status_code=303)


# (Optional) keep this legacy single-set endpoint in case anything still calls it.
@app.post("/meal_ingredient/set")
def ui_meal_ingredient_set(
    request: Request,
    meal_id: int = Form(...),
    ingredient_id: int = Form(...),
    amount_per_person: float = Form(...),
):
    with get_db() as con:
        con.execute(
            """
            INSERT INTO meal_ingredients(meal_id, ingredient_id, amount_per_person)
            VALUES(?,?,?)
            ON CONFLICT(meal_id, ingredient_id)
            DO UPDATE SET amount_per_person=excluded.amount_per_person
            """,
            (meal_id, ingredient_id, amount_per_person),
        )
    base = ingress_base(request)
    return RedirectResponse(url=f"{base}/meals?meal_id={meal_id}", status_code=303)


# --------------------
# Planner UI
# --------------------
@app.get("/planner", response_class=HTMLResponse)
def ui_planner(request: Request, start: str | None = None):
    base = ingress_base(request)
    slots = get_default_slots()

    if start:
        start_date = date.fromisoformat(start)
    else:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())

    ensure_plan_rows_for_week(start_date, 7)

    with get_db() as con:
        meals = con.execute("SELECT * FROM meals ORDER BY name").fetchall()
        plan_rows = con.execute(
            """
            SELECT p.day, p.slot, p.servings, p.meal_id, m.name as meal_name
            FROM plan p
            LEFT JOIN meals m ON m.id = p.meal_id
            WHERE p.day BETWEEN ? AND ?
            ORDER BY p.day, p.slot
            """,
            (start_date.isoformat(), (start_date + timedelta(days=6)).isoformat()),
        ).fetchall()

    plan: dict[str, dict[str, dict]] = {}
    for r in plan_rows:
        plan.setdefault(r["day"], {})[r["slot"]] = dict(r)

    days = [start_date + timedelta(days=i) for i in range(7)]

    return templates.TemplateResponse(
        "planner.html",
        {
            "request": request,
            "ingress": base,
            "slots": slots,
            "days": days,
            "plan": plan,
            "meals": meals,
            "start_date": start_date,
        },
    )


@app.post("/planner/set")
def ui_planner_set(
    request: Request,
    day: str = Form(...),
    slot: str = Form(...),
    meal_id: int | None = Form(None),
    servings: int = Form(2),
):
    with get_db() as con:
        con.execute(
            """
            INSERT INTO plan(day, slot, meal_id, servings)
            VALUES(?,?,?,?)
            ON CONFLICT(day, slot)
            DO UPDATE SET meal_id=excluded.meal_id, servings=excluded.servings
            """,
            (day, slot, meal_id if meal_id else None, int(servings)),
        )

    base = ingress_base(request)
    return RedirectResponse(url=f"{base}/planner?start={day}", status_code=303)


# --------------------
# API (used by HA integration)
# --------------------
def _get_meal_for_day_slot(d: date, slot: str):
    with get_db() as con:
        row = con.execute(
            """
            SELECT p.day, p.slot, p.servings, m.id as meal_id, m.name as meal_name, m.notes
            FROM plan p
            LEFT JOIN meals m ON m.id = p.meal_id
            WHERE p.day=? AND p.slot=?
            """,
            (d.isoformat(), slot),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def _shopping_aggregate(start_date: date, days: int):
    end_date = start_date + timedelta(days=days - 1)

    with get_db() as con:
        rows = con.execute(
            """
            SELECT p.day, p.slot, p.servings, m.id as meal_id, m.name as meal_name,
                   i.name as ingredient_name, i.unit, i.rounding, mi.amount_per_person
            FROM plan p
            JOIN meals m ON m.id = p.meal_id
            JOIN meal_ingredients mi ON mi.meal_id = m.id
            JOIN ingredients i ON i.id = mi.ingredient_id
            WHERE p.day BETWEEN ? AND ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()

    agg: dict[tuple[str, str, str], float] = {}
    for r in rows:
        key = (r["ingredient_name"], r["unit"], r["rounding"])
        qty = float(r["amount_per_person"]) * int(r["servings"])
        agg[key] = agg.get(key, 0.0) + qty

    items = []
    for (name, unit, rounding), qty in sorted(agg.items(), key=lambda x: x[0][0].lower()):
        qty2 = _round_qty(qty, rounding)
        items.append(
            {
                "name": name,
                "qty": qty2,
                "qty_display": _fmt_qty(qty2),
                "unit": unit,
                "rounding": rounding,
            }
        )
    return items


@app.get("/api/today")
def api_today(slot: str = "dinner"):
    d = date.today()
    meal = _get_meal_for_day_slot(d, slot)
    return {"date": d.isoformat(), "slot": slot, "meal": meal}


@app.get("/api/tomorrow")
def api_tomorrow(slot: str = "dinner"):
    d = date.today() + timedelta(days=1)
    meal = _get_meal_for_day_slot(d, slot)
    return {"date": d.isoformat(), "slot": slot, "meal": meal}


@app.get("/api/shopping_list")
def api_shopping_list(weeks: int = 1, start: str | None = None):
    if weeks not in (1, 2):
        return JSONResponse({"error": "weeks must be 1 or 2"}, status_code=400)

    if start:
        start_date = date.fromisoformat(start)
    else:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())

    ensure_plan_rows_for_week(start_date, weeks * 7)
    items = _shopping_aggregate(start_date, weeks * 7)
    return {"start": start_date.isoformat(), "weeks": weeks, "items": items}


@app.get("/health")
def health():
    return {"status": "ok"}