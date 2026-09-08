from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from models import MealPlanEntry, Recipe, RecipeIngredient, UsageHistory, WeeklyMealPlan


WEEK_INDEX_EPOCH = date(1970, 1, 5)


def _active(row: dict[str, Any]) -> bool:
    return not row.get("deletedAt")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _week_date(value: Any) -> date | None:
    """Convert the export's week index (weeks since Monday 1970-01-05)."""
    if isinstance(value, (int, float)) and int(value) == value:
        return WEEK_INDEX_EPOCH + timedelta(weeks=int(value))
    return _date(value)


def import_external_data(db: Session, payload: dict[str, Any]) -> dict[str, int]:
    products = {
        str(row.get("id")): row
        for row in payload.get("products", [])
        if isinstance(row, dict) and row.get("id") and _active(row) and _text(row.get("name"))
    }
    recipes = {
        str(row.get("id")): row
        for row in payload.get("recipes", [])
        if isinstance(row, dict) and row.get("id") and _active(row) and _text(row.get("name"))
    }
    aisles = {
        str(row.get("id")): _text(row.get("name"))
        for row in payload.get("aisles", [])
        if isinstance(row, dict) and row.get("id")
    }
    product_aisle = {
        str(row.get("productId", row.get("product_id"))): aisles.get(
            str(row.get("aisleId", row.get("aisle_id"))), ""
        )
        for row in payload.get("product_aisles", [])
        if isinstance(row, dict)
    }
    recipe_ids: dict[str, int] = {}
    product_names: dict[str, str] = {}
    imported_recipes = imported_ingredients = 0

    for external_id, source in recipes.items():
        name = _text(source["name"])
        recipe = db.query(Recipe).filter(Recipe.name == name).first()
        if recipe is None:
            recipe = Recipe(name=name, description=None, servings=4)
            db.add(recipe)
            db.flush()
            imported_recipes += 1
        recipe_ids[external_id] = recipe.id

    for external_id, source in products.items():
        product_names[external_id] = _text(source["name"])

    relations = payload.get("products_recipies", payload.get("products_recipes", []))
    grouped: dict[str, list[RecipeIngredient]] = {}
    for relation in relations:
        if not isinstance(relation, dict) or not _active(relation):
            continue
        recipe_key = relation.get("recipeId", relation.get("recipe_id"))
        product_key = relation.get("productId", relation.get("product_id"))
        recipe_id = recipe_ids.get(str(recipe_key))
        product = products.get(str(product_key))
        if recipe_id is None or product is None:
            continue
        name = product_names[str(product_key)]
        grouped.setdefault(str(recipe_id), []).append(
            RecipeIngredient(
                name=name,
                quantity=_number(relation.get("amount", relation.get("quantity"))),
                unit=_text(relation.get("unit")) or None,
                category=product_aisle.get(str(product_key)) or None,
            )
        )

    for recipe_id, ingredients in grouped.items():
        recipe = db.get(Recipe, int(recipe_id))
        if recipe is None:
            continue
        recipe.ingredients = ingredients
        imported_ingredients += len(ingredients)

    imported_plans = 0
    imported_usages = 0
    schedule = payload.get("schedule", [])
    positions: dict[tuple[date, int], int] = {}
    for source in schedule:
        if not isinstance(source, dict) or not _active(source):
            continue
        monday = _week_date(source.get("week", source.get("monday")))
        recipe_id = recipe_ids.get(str(source.get("recipeId", source.get("recipe_id"))))
        if monday is None or monday.weekday() != 0 or recipe_id is None:
            continue
        plan = db.query(WeeklyMealPlan).filter(WeeklyMealPlan.monday == monday).first()
        if plan is None:
            plan = WeeklyMealPlan(monday=monday)
            db.add(plan)
            db.flush()
            imported_plans += 1
        try:
            day = int(source.get("day", source.get("day_of_week", 0)))
        except (TypeError, ValueError):
            continue
        if not 0 <= day <= 6:
            continue
        meal = _text(source.get("meal", source.get("mealType", "comida"))) or "comida"
        position_key = (monday, day)
        position = positions.get(position_key, 0)
        positions[position_key] = position + 1
        exists = next((entry for entry in plan.entries if entry.day_of_week == day and entry.meal_type == meal and entry.position == position), None)
        if exists is None:
            plan.entries.append(MealPlanEntry(day_of_week=day, meal_type=meal, position=position, recipe_id=recipe_id))

        used_at = datetime.combine(monday + timedelta(days=day), time.min)
        already_used = db.scalar(
            select(UsageHistory.id).where(
                UsageHistory.recipe_id == recipe_id,
                UsageHistory.monday == monday,
                UsageHistory.meal_type == meal,
                UsageHistory.used_at == used_at,
            )
        )
        if already_used is None:
            db.add(UsageHistory(recipe_id=recipe_id, monday=monday, meal_type=meal, used_at=used_at))
            imported_usages += 1

    db.commit()
    return {
        "recipes": len(recipes),
        "new_recipes": imported_recipes,
        "ingredients": imported_ingredients,
        "plans": imported_plans,
        "usages": imported_usages,
    }
