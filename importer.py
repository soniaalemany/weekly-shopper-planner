from datetime import date, datetime, time, timedelta
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from models import MealPlanEntry, Recipe, RecipeIngredient, UsageHistory, WeeklyMealPlan


WEEK_INDEX_EPOCH = date(1970, 1, 5)
NATIVE_FORMAT = "weekly-shopper-planner"
NATIVE_VERSION = 1

_QUANTITY_RE = re.compile(
    r"(?P<quantity>\d+(?:[.,]\d+)?)(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?"
    r"(?:\s*(?P<unit>[^\d,.;()]+?))?(?=\s*(?:\(|$|,|;))",
    re.IGNORECASE,
)


def parse_markdown_recipes(content: str) -> list[dict[str, Any]]:
    """Parse recipes formatted as `## Name` followed by `- Ingredient: amount`."""
    parsed: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = {"name": heading.group(1).strip(), "ingredients": []}
            parsed.append(current)
            continue
        if current is None or not line.startswith("-"):
            continue
        ingredient_line = line[1:].strip()
        if ":" not in ingredient_line:
            continue
        name, details = (part.strip() for part in ingredient_line.split(":", 1))
        if not name:
            continue
        match = _QUANTITY_RE.search(details)
        quantity = None
        unit = None
        if match:
            quantity = _number(match.group("quantity").replace(",", "."))
            unit = _text(match.group("unit")) or None
        current["ingredients"].append(
            {"name": name, "quantity": quantity, "unit": unit}
        )
    return [recipe for recipe in parsed if recipe["ingredients"]]


def import_markdown_recipes(db: Session, content: str) -> dict[str, int]:
    recipes = parse_markdown_recipes(content)
    imported_recipes = imported_ingredients = 0
    for source in recipes:
        name = _text(source["name"])
        recipe = db.query(Recipe).filter(Recipe.name == name).first()
        if recipe is None:
            recipe = Recipe(name=name, description=None, servings=2)
            db.add(recipe)
            db.flush()
            imported_recipes += 1
        recipe.ingredients = [
            RecipeIngredient(
                name=item["name"],
                quantity=item["quantity"],
                unit=item["unit"],
            )
            for item in source["ingredients"]
        ]
        imported_ingredients += len(recipe.ingredients)
    db.commit()
    return {
        "recipes": len(recipes),
        "new_recipes": imported_recipes,
        "ingredients": imported_ingredients,
    }


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


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


def export_data(db: Session) -> dict[str, Any]:
    recipes = list(
        db.query(Recipe)
        .options(selectinload(Recipe.ingredients))
        .order_by(Recipe.name)
        .all()
    )
    recipe_data = [
        {
            "id": recipe.external_id,
            "name": recipe.name,
            "description": recipe.description,
            "instructions": recipe.instructions,
            "servings": recipe.servings,
            "prep_minutes": recipe.prep_minutes,
            "ingredients": [
                {
                    "name": ingredient.name,
                    "quantity": ingredient.quantity,
                    "unit": ingredient.unit,
                    "category": ingredient.category,
                }
                for ingredient in recipe.ingredients
            ],
        }
        for recipe in recipes
    ]
    plans = list(
        db.query(WeeklyMealPlan)
        .options(selectinload(WeeklyMealPlan.entries).selectinload(MealPlanEntry.recipe))
        .order_by(WeeklyMealPlan.monday)
        .all()
    )
    plan_data = [
        {
            "monday": _iso(plan.monday),
            "entries": [
                {
                    "day_of_week": entry.day_of_week,
                    "meal_type": entry.meal_type,
                    "position": entry.position,
                    "recipe_id": entry.recipe.external_id,
                    "servings": entry.servings,
                }
                for entry in sorted(plan.entries, key=lambda item: (item.day_of_week, item.meal_type, item.position))
            ],
        }
        for plan in plans
    ]
    usages = list(db.query(UsageHistory).order_by(UsageHistory.used_at).all())
    usage_data = [
        {
            "recipe_id": usage.recipe.external_id if usage.recipe else None,
            "monday": _iso(usage.monday),
            "meal_type": usage.meal_type,
            "used_at": _iso(usage.used_at),
        }
        for usage in usages
        if usage.recipe is not None
    ]
    return {
        "format": NATIVE_FORMAT,
        "version": NATIVE_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "recipes": recipe_data,
        "meal_plans": plan_data,
        "usage_history": usage_data,
    }


def import_native_data(db: Session, payload: dict[str, Any]) -> dict[str, int]:
    if payload.get("version") != NATIVE_VERSION:
        raise ValueError(f"Unsupported export version: {payload.get('version')}")
    source_recipes = payload.get("recipes")
    source_plans = payload.get("meal_plans", [])
    source_usages = payload.get("usage_history", [])
    if not isinstance(source_recipes, list) or not isinstance(source_plans, list) or not isinstance(source_usages, list):
        raise ValueError("Invalid export structure")

    recipes_by_external_id: dict[str, Recipe] = {}
    created_recipes = updated_recipes = imported_ingredients = 0
    for source in source_recipes:
        if not isinstance(source, dict) or not _text(source.get("id")) or not _text(source.get("name")):
            raise ValueError("Each exported recipe requires id and name")
        external_id = _text(source["id"])
        recipe = db.query(Recipe).filter(Recipe.external_id == external_id).first()
        if recipe is None:
            recipe = db.query(Recipe).filter(Recipe.name == _text(source["name"])).first()
        if recipe is None:
            recipe = Recipe(external_id=external_id, name=_text(source["name"]), servings=4)
            db.add(recipe)
            db.flush()
            created_recipes += 1
        else:
            recipe.external_id = external_id
            updated_recipes += 1
        for field in ("name", "description", "instructions", "servings", "prep_minutes"):
            if field in source:
                setattr(recipe, field, source[field])
        ingredients = source.get("ingredients", [])
        if not isinstance(ingredients, list):
            raise ValueError(f"Invalid ingredients for recipe {external_id}")
        recipe.ingredients = [
            RecipeIngredient(
                name=_text(item.get("name")),
                quantity=_number(item.get("quantity")),
                unit=_text(item.get("unit")) or None,
                category=_text(item.get("category")) or None,
            )
            for item in ingredients
            if isinstance(item, dict) and _text(item.get("name"))
        ]
        imported_ingredients += len(recipe.ingredients)
        recipes_by_external_id[external_id] = recipe

    imported_plans = 0
    for source in source_plans:
        if not isinstance(source, dict):
            raise ValueError("Invalid meal plan")
        monday = _date(source.get("monday"))
        if monday is None or monday.weekday() != 0:
            raise ValueError("Meal plan monday must be a Monday")
        entries = source.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("Invalid meal plan entries")
        plan = db.query(WeeklyMealPlan).filter(WeeklyMealPlan.monday == monday).first()
        if plan is None:
            plan = WeeklyMealPlan(monday=monday)
            db.add(plan)
            db.flush()
            imported_plans += 1
        plan.entries.clear()
        db.flush()
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError("Invalid meal plan entry")
            recipe = recipes_by_external_id.get(_text(item.get("recipe_id")))
            if recipe is None:
                raise ValueError(f"Unknown recipe reference: {item.get('recipe_id')}")
            plan.entries.append(
                MealPlanEntry(
                    day_of_week=int(item["day_of_week"]),
                    meal_type=_text(item["meal_type"]),
                    position=int(item.get("position", 0)),
                    recipe_id=recipe.id,
                    servings=item.get("servings"),
                )
            )

    imported_usages = 0
    for source in source_usages:
        if not isinstance(source, dict):
            raise ValueError("Invalid usage history entry")
        recipe = recipes_by_external_id.get(_text(source.get("recipe_id")))
        if recipe is None:
            raise ValueError(f"Unknown usage recipe reference: {source.get('recipe_id')}")
        monday = _date(source.get("monday"))
        used_at = datetime.fromisoformat(source["used_at"].replace("Z", "+00:00")).replace(tzinfo=None) if source.get("used_at") else datetime.now()
        exists = db.scalar(
            select(UsageHistory.id).where(
                UsageHistory.recipe_id == recipe.id,
                UsageHistory.monday == monday,
                UsageHistory.meal_type == source.get("meal_type"),
                UsageHistory.used_at == used_at,
            )
        )
        if exists is None:
            db.add(UsageHistory(recipe_id=recipe.id, monday=monday, meal_type=source.get("meal_type"), used_at=used_at))
            imported_usages += 1
    db.commit()
    return {
        "recipes": len(source_recipes),
        "new_recipes": created_recipes,
        "updated_recipes": updated_recipes,
        "ingredients": imported_ingredients,
        "plans": imported_plans,
        "usages": imported_usages,
    }
