import os
from datetime import date
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from crud import *
from database import Base, engine, get_db, migrate_meal_plan_entries
from models import Recipe as RecipeModel, ShoppingList as ShoppingListModel, ShoppingListItem as ShoppingListItemModel, UsageHistory as UsageHistoryModel
from importer import import_external_data, import_markdown_recipes
from schemas import *

Base.metadata.create_all(bind=engine)
migrate_meal_plan_entries()
app = FastAPI(title="Weekly Meal Planner API", version="1.0.0")
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=origins != ["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health(): return {"status": "ok"}

@app.post("/api/import")
def import_data(payload: dict, db: Session = Depends(get_db)):
    try:
        return import_external_data(db, payload)
    except Exception:
        db.rollback()
        raise

@app.post("/api/import-markdown")
def import_markdown(payload: dict, db: Session = Depends(get_db)):
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(422, "Markdown content is required")
    try:
        return import_markdown_recipes(db, content)
    except Exception:
        db.rollback()
        raise

@app.get("/api/recipes", response_model=list[Recipe])
def recipes(db: Session = Depends(get_db)): return list_recipes(db)
@app.post("/api/recipes", response_model=Recipe, status_code=201)
def create_recipe_endpoint(data: RecipeCreate, db: Session = Depends(get_db)): return create_recipe(db, data)
@app.get("/api/recipes/{recipe_id}", response_model=Recipe)
def recipe(recipe_id: int, db: Session = Depends(get_db)):
    value = get_recipe(db, recipe_id)
    if not value: raise HTTPException(404, "Recipe not found")
    return value
@app.put("/api/recipes/{recipe_id}", response_model=Recipe)
def update_recipe_endpoint(recipe_id: int, data: RecipeUpdate, db: Session = Depends(get_db)):
    value = get_recipe(db, recipe_id)
    if not value: raise HTTPException(404, "Recipe not found")
    return update_recipe(db, value, data)
@app.delete("/api/recipes/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    value = get_recipe(db, recipe_id)
    if not value: raise HTTPException(404, "Recipe not found")
    db.delete(value); db.commit()

@app.get("/api/recipes/{recipe_id}/usage-history", response_model=list[UsageHistory])
def recipe_usage_history(recipe_id: int, db: Session = Depends(get_db)):
    if not get_recipe(db, recipe_id):
        raise HTTPException(404, "Recipe not found")
    query = select(UsageHistoryModel).where(UsageHistoryModel.recipe_id == recipe_id).order_by(UsageHistoryModel.monday.desc())
    return list(db.scalars(query).all())

@app.get("/api/meal-plans", response_model=list[MealPlan])
def meal_plans(db: Session = Depends(get_db)):
    return list(db.scalars(plan_query().order_by(WeeklyMealPlan.monday.desc())).all())

@app.get("/api/meal-plans/{monday}", response_model=MealPlan)
def meal_plan(monday: date, db: Session = Depends(get_db)):
    if monday.weekday() != 0: raise HTTPException(422, "Date must be a Monday")
    value = get_plan(db, monday)
    if not value: raise HTTPException(404, "Meal plan not found")
    return value
@app.put("/api/meal-plans/{monday}", response_model=MealPlan)
def put_meal_plan(monday: date, data: MealPlanCreate, db: Session = Depends(get_db)):
    if monday.weekday() != 0: raise HTTPException(422, "Date must be a Monday")
    data.monday = monday
    positions = {(entry.day_of_week, entry.meal_type, entry.position) for entry in data.entries}
    if len(positions) != len(data.entries):
        raise HTTPException(422, "Duplicate recipe position in meal slot")
    for entry in data.entries:
        if not get_recipe(db, entry.recipe_id): raise HTTPException(400, f"Recipe {entry.recipe_id} not found")
    return save_plan(db, data)
@app.delete("/api/meal-plans/{monday}", status_code=204)
def delete_meal_plan(monday: date, db: Session = Depends(get_db)):
    value = get_plan(db, monday)
    if not value: raise HTTPException(404, "Meal plan not found")
    db.delete(value); db.commit()

@app.post("/api/shopping-lists/generate/{monday}", response_model=ShoppingList)
def generate_list(monday: date, db: Session = Depends(get_db)):
    if monday.weekday() != 0: raise HTTPException(422, "Date must be a Monday")
    value = generate_shopping_list(db, monday)
    if not value: raise HTTPException(404, "Meal plan not found")
    return value
@app.post("/api/meal-plans/{monday}/generate-shopping-list", response_model=ShoppingList)
def generate_plan_shopping_list(monday: date, db: Session = Depends(get_db)):
    if monday.weekday() != 0: raise HTTPException(422, "Date must be a Monday")
    value = generate_shopping_list(db, monday)
    if not value: raise HTTPException(404, "Meal plan not found")
    return value
@app.get("/api/shopping-lists/{monday}", response_model=ShoppingList)
def shopping_list(monday: date, db: Session = Depends(get_db)):
    value = db.scalar(select(ShoppingListModel).options(selectinload(ShoppingListModel.items)).where(ShoppingListModel.monday == monday))
    if not value: raise HTTPException(404, "Shopping list not found")
    return value
@app.put("/api/shopping-lists/{monday}", response_model=ShoppingList)
def put_shopping_list(monday: date, data: ShoppingListUpdate, db: Session = Depends(get_db)):
    value = db.scalar(select(ShoppingListModel).options(selectinload(ShoppingListModel.items)).where(ShoppingListModel.monday == monday))
    if value is None:
        value = ShoppingListModel(monday=monday)
        db.add(value)
        db.flush()
    else:
        value.items.clear()
        db.flush()
    value.items = [ShoppingListItemModel(**item.model_dump()) for item in data.items]
    db.commit()
    db.refresh(value)
    return value
@app.patch("/api/shopping-lists/items/{item_id}", response_model=ShoppingItem)
def check_item(item_id: int, data: ShoppingItemUpdate, db: Session = Depends(get_db)):
    value = db.get(ShoppingListItemModel, item_id)
    if not value: raise HTTPException(404, "Shopping item not found")
    value.checked = data.checked; db.commit(); db.refresh(value); return value
@app.put("/api/shopping-lists/{monday}/items/{item_id}", response_model=ShoppingItem)
def update_list_item(monday: date, item_id: int, data: ShoppingItemBase, db: Session = Depends(get_db)):
    value = db.scalar(select(ShoppingListItemModel).join(ShoppingListModel).where(ShoppingListModel.monday == monday, ShoppingListItemModel.id == item_id))
    if not value: raise HTTPException(404, "Shopping item not found")
    for key, item_value in data.model_dump().items(): setattr(value, key, item_value)
    db.commit(); db.refresh(value); return value

@app.get("/api/usage-history", response_model=list[UsageHistory])
def usage_history(recipe_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    query = select(UsageHistoryModel).options(selectinload(UsageHistoryModel.recipe).selectinload(RecipeModel.ingredients)).order_by(UsageHistoryModel.used_at.desc())
    if recipe_id is not None: query = query.where(UsageHistoryModel.recipe_id == recipe_id)
    return list(db.scalars(query).all())
@app.post("/api/usage-history", response_model=UsageHistory, status_code=201)
def record_usage(data: UsageCreate, db: Session = Depends(get_db)):
    if not get_recipe(db, data.recipe_id): raise HTTPException(400, "Recipe not found")
    value = UsageHistoryModel(**data.model_dump()); db.add(value); db.commit(); db.refresh(value)
    return db.scalar(select(UsageHistoryModel).options(selectinload(UsageHistoryModel.recipe).selectinload(RecipeModel.ingredients)).where(UsageHistoryModel.id == value.id))

# Serve only the frontend assets; the project root also contains backend source files.
frontend_dir = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parent))
if frontend_dir.is_dir():
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(frontend_dir / "index.html")

    @app.get("/recipes.html", include_in_schema=False)
    def recipes_page():
        return FileResponse(frontend_dir / "recipes.html")

    @app.get("/shopping.html", include_in_schema=False)
    def shopping_page():
        return FileResponse(frontend_dir / "shopping.html")

    @app.get("/{asset_name}", include_in_schema=False)
    def frontend_asset(asset_name: str):
        allowed_assets = {"styles.css", "app.js", "recipes.js", "shopping.js"}
        if asset_name not in allowed_assets:
            raise HTTPException(404, "Asset not found")
        return FileResponse(frontend_dir / asset_name)
