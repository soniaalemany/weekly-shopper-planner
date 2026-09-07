from datetime import date, datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Recipe(Base):
    __tablename__ = "recipes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    servings: Mapped[int] = mapped_column(Integer, default=4)
    prep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")

class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")

class WeeklyMealPlan(Base):
    __tablename__ = "weekly_meal_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    monday: Mapped[date] = mapped_column(Date, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    entries: Mapped[list["MealPlanEntry"]] = relationship(back_populates="plan", cascade="all, delete-orphan")

class MealPlanEntry(Base):
    __tablename__ = "meal_plan_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("weekly_meal_plans.id", ondelete="CASCADE"), index=True)
    day_of_week: Mapped[int] = mapped_column("day", Integer)  # 0=Monday, 6=Sunday
    meal_type: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="RESTRICT"))
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan: Mapped[WeeklyMealPlan] = relationship(back_populates="entries")
    recipe: Mapped[Recipe] = relationship()
    __table_args__ = (UniqueConstraint("plan_id", "day", "meal_type", "position", name="uq_plan_day_meal_position"),)

class ShoppingList(Base):
    __tablename__ = "shopping_lists"
    id: Mapped[int] = mapped_column(primary_key=True)
    monday: Mapped[date | None] = mapped_column(Date, unique=True, index=True, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    items: Mapped[list["ShoppingListItem"]] = relationship(back_populates="shopping_list", cascade="all, delete-orphan")

class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    shopping_list_id: Mapped[int] = mapped_column(ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    checked: Mapped[bool] = mapped_column(default=False)
    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items")

class UsageHistory(Base):
    __tablename__ = "usage_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    monday: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    meal_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recipe: Mapped[Recipe] = relationship()
