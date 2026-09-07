from datetime import date, datetime
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

class IngredientBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=80)
class IngredientCreate(IngredientBase): pass
class Ingredient(IngredientBase):
    model_config = ConfigDict(from_attributes=True)
    id: int

class RecipeBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    instructions: str | None = None
    servings: int = Field(default=4, ge=1)
    prep_minutes: int | None = Field(default=None, ge=0)
class RecipeCreate(RecipeBase):
    ingredients: list[IngredientCreate] = []
class RecipeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    instructions: str | None = None
    servings: int | None = Field(default=None, ge=1)
    prep_minutes: int | None = Field(default=None, ge=0)
    ingredients: list[IngredientCreate] | None = None
class Recipe(RecipeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ingredients: list[Ingredient] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_used_date: date | None = None
    usage_count: int = 0

class MealEntryCreate(BaseModel):
    day_of_week: int = Field(
        ge=0, le=6, description="0 Monday through 6 Sunday",
        validation_alias=AliasChoices("day_of_week", "day"),
    )
    meal_type: str = Field(min_length=1, max_length=40)
    position: int = Field(default=0, ge=0, le=1)
    recipe_id: int
    servings: int | None = Field(default=None, ge=1)
class MealEntry(MealEntryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recipe: Recipe | None = None
class MealPlanCreate(BaseModel):
    monday: date | None = None
    entries: list[MealEntryCreate] = []
    @field_validator("monday")
    @classmethod
    def must_be_monday(cls, value: date | None) -> date | None:
        if value is None:
            return value
        if value.weekday() != 0:
            raise ValueError("monday must be a Monday")
        return value
class MealPlan(MealPlanCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entries: list[MealEntry] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None

class ShoppingItemBase(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    category: str | None = None
    checked: bool = False
class ShoppingItem(ShoppingItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
class ShoppingList(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    monday: date | None = None
    generated_at: datetime | None = None
    items: list[ShoppingItem] = []
class ShoppingListUpdate(BaseModel):
    items: list[ShoppingItemBase] = []
class ShoppingItemUpdate(BaseModel):
    checked: bool

class UsageCreate(BaseModel):
    recipe_id: int
    monday: date | None = None
    meal_type: str | None = None
class UsageHistory(UsageCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    used_at: datetime | None = None
    recipe: Recipe | None = None
