# Planificador semanal de comidas

Aplicación web para organizar menús semanales, guardar recetas y generar listas
de la compra. El backend está construido con FastAPI, SQLAlchemy y SQLite; la
interfaz usa HTML, CSS y JavaScript sin framework.

El proyecto está inspirado en
[lista_de_la_compra](https://github.com/jaimegonzalezfabregas/lista_de_la_compra).
La importación de archivos JSON permite migrar a esta aplicación los datos
exportados desde esa aplicación original.

Todo el código de este proyecto ha sido generado con GitHub Copilot.

## Funcionalidades

- Crear, editar y eliminar recetas con sus ingredientes.
- Planificar recetas por día, tipo de comida y posición.
- Consultar las semanas guardadas.
- Generar una lista de la compra a partir del menú semanal.
- Importar un catálogo y su histórico desde un archivo JSON en la sección
  **Recetas**.
- Persistir los datos en SQLite.

## Requisitos

- Python 3.12 o posterior.
- Docker y Docker Compose (opcional).

Los archivos `requirements.txt` se mantienen fuera del repositorio. Para una
instalación local, instala las dependencias directamente:

```bash
python -m pip install "fastapi>=0.110,<1.0" "uvicorn[standard]>=0.29,<1.0" \
  "SQLAlchemy>=2.0,<3.0" "pydantic>=2.0,<3.0"
```

## Ejecutar en local

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install "fastapi>=0.110,<1.0" "uvicorn[standard]>=0.29,<1.0" \
  "SQLAlchemy>=2.0,<3.0" "pydantic>=2.0,<3.0"
uvicorn backend.main:app --host 127.0.0.1 --port 9009 --reload
```

Abre <http://localhost:9009>. La base de datos local se crea como
`meal_planner.db` en la raíz del proyecto. Este archivo está excluido de Git.

## Ejecutar con Docker

```bash
docker compose up --build
```

Abre <http://localhost:9009>. El puerto del host se puede cambiar sin modificar
el puerto interno:

```bash
PORT=9010 docker compose up --build
```

Los datos se conservan en el volumen Docker `meal_planner_data`. Para detener
los servicios:

```bash
docker compose down
```

## API

La documentación interactiva está disponible en:

- <http://localhost:9009/docs>
- <http://localhost:9009/redoc>

La comprobación de salud responde en `GET /api/health`.

## Migrar datos desde lista_de_la_compra

En **Recetas**, selecciona el JSON exportado desde
**lista_de_la_compra** y pulsa **Cargar datos**. Se importan las recetas
activas, sus ingredientes, las semanas del planificador y el historial de uso.
Las semanas se normalizan al lunes correspondiente y volver a cargar el mismo
archivo no duplica planes ni usos.

## Estructura

```text
backend/    API FastAPI, modelos, persistencia e importador
frontend/   páginas y recursos estáticos de la interfaz
Dockerfile  imagen de producción
docker-compose.yml
```
