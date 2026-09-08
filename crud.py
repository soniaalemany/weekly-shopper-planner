from collections import defaultdict
from datetime import date
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload
from models import *

def recipe_query():
    return select(Recipe).options(selectinload(Recipe.ingredients))
def _add_usage_stats(db, recipes):
    ids = [recipe.id for recipe in recipes]
    stats = db.execute(
        select(UsageHistory.recipe_id, func.count(UsageHistory.id), func.max(UsageHistory.used_at))
        .where(UsageHistory.recipe_id.in_(ids))
        .group_by(UsageHistory.recipe_id)
    ).all() if ids else []
    by_id = {row[0]: (row[1], row[2]) for row in stats}
    for recipe in recipes:
        count, last_used = by_id.get(recipe.id, (0, None))
        recipe.usage_count = count
        recipe.last_used_date = last_used.date() if last_used else None
    return recipes
def list_recipes(db): return _add_usage_stats(db, list(db.scalars(recipe_query().order_by(Recipe.name)).all()))
def get_recipe(db, recipe_id):
    recipe = db.scalar(recipe_query().where(Recipe.id == recipe_id))
    return _add_usage_stats(db, [recipe])[0] if recipe else None
def create_recipe(db, data):
    recipe = Recipe(**data.model_dump(exclude={"ingredients"}))
    recipe.ingredients = [RecipeIngredient(**i.model_dump()) for i in data.ingredients]
    db.add(recipe); db.commit(); db.refresh(recipe); return get_recipe(db, recipe.id)
def update_recipe(db, recipe, data):
    values = data.model_dump(exclude_unset=True)
    ingredients = values.pop("ingredients", None)
    for key, value in values.items(): setattr(recipe, key, value)
    if ingredients is not None: recipe.ingredients = [RecipeIngredient(**i) for i in ingredients]
    db.commit(); return get_recipe(db, recipe.id)

def plan_query(): return select(WeeklyMealPlan).options(selectinload(WeeklyMealPlan.entries).selectinload(MealPlanEntry.recipe).selectinload(Recipe.ingredients))
def get_plan(db, monday): return db.scalar(plan_query().where(WeeklyMealPlan.monday == monday))
def save_plan(db, data):
    plan = get_plan(db, data.monday)
    if plan is None: plan = WeeklyMealPlan(monday=data.monday); db.add(plan); db.flush()
    else: plan.entries.clear(); db.flush()
    db.execute(delete(UsageHistory).where(UsageHistory.monday == data.monday))
    used_recipes = set()
    grouped_entries = defaultdict(list)
    for entry in data.entries:
        grouped_entries[(entry.day_of_week, entry.meal_type)].append(entry)
    for (day_of_week, meal_type), entries in grouped_entries.items():
        for position, entry in enumerate(sorted(entries, key=lambda item: item.position)):
            plan.entries.append(MealPlanEntry(day_of_week=day_of_week, meal_type=meal_type, position=position, recipe_id=entry.recipe_id, servings=entry.servings))
            used_recipes.add(entry.recipe_id)
    for recipe_id in used_recipes:
        db.add(UsageHistory(recipe_id=recipe_id, monday=data.monday))
    db.commit(); return get_plan(db, data.monday)

def generate_shopping_list(db, monday):
    plan = get_plan(db, monday)
    if not plan: return None
    shopping = db.scalar(select(ShoppingList).where(ShoppingList.monday == monday))
    if shopping is None: shopping = ShoppingList(monday=monday); db.add(shopping); db.flush()
    else: shopping.items.clear(); db.flush()
    totals = defaultdict(float); meta = {}
    for entry in plan.entries:
        scale = (entry.servings or entry.recipe.servings) / entry.recipe.servings
        for ingredient in entry.recipe.ingredients:
            key = (ingredient.name.strip().lower(), (ingredient.unit or "").strip().lower())
            if ingredient.quantity is not None: totals[key] += ingredient.quantity * scale
            meta[key] = ingredient
    for (name, unit), total in sorted(totals.items()):
        source = meta[(name, unit)]
        shopping.items.append(ShoppingListItem(name=source.name, quantity=total, unit=source.unit, category=source.category))
    # Keep ingredients without quantities too.
    for (name, unit), source in meta.items():
        if (name, unit) not in totals: shopping.items.append(ShoppingListItem(name=source.name, unit=source.unit, category=source.category))
    db.commit(); db.refresh(shopping); return shopping
