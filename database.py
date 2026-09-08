import os
from collections.abc import Generator
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./meal_planner.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def migrate_meal_plan_entries() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("meal_plan_entries")}
        if not columns or "position" in columns:
            return
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("""
            CREATE TABLE meal_plan_entries_new (
                id INTEGER NOT NULL PRIMARY KEY,
                plan_id INTEGER NOT NULL,
                day INTEGER NOT NULL,
                meal_type VARCHAR(40) NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                recipe_id INTEGER NOT NULL,
                servings INTEGER,
                CONSTRAINT uq_plan_day_meal_position UNIQUE (plan_id, day, meal_type, position),
                FOREIGN KEY(plan_id) REFERENCES weekly_meal_plans (id) ON DELETE CASCADE,
                FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE RESTRICT
            )
        """))
        connection.execute(text("""
            INSERT INTO meal_plan_entries_new
                (id, plan_id, day, meal_type, position, recipe_id, servings)
            SELECT id, plan_id, day, meal_type, 0, recipe_id, servings
            FROM meal_plan_entries
        """))
        connection.execute(text("DROP TABLE meal_plan_entries"))
        connection.execute(text("ALTER TABLE meal_plan_entries_new RENAME TO meal_plan_entries"))
        connection.execute(text("PRAGMA foreign_keys=ON"))
