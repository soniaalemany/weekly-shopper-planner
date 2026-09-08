FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    "fastapi>=0.110,<1.0" \
    "uvicorn[standard]>=0.29,<1.0" \
    "SQLAlchemy>=2.0,<3.0" \
    "pydantic>=2.0,<3.0"
COPY . .
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/meal_planner.db
EXPOSE 9009
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","9009"]
