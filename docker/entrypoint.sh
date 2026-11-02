#!/bin/sh
set -e

echo "Building food database from CSV..."
python scripts/build_database.py \
    --csv ../data/daily_food_nutrition_dataset.csv \
    --db ../data/foods.db

echo "Validating Expert System Knowledge Base..."
python -m app.expert.lint

echo "Starting application..."
exec "$@"
