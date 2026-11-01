#!/bin/sh
set -e

echo "Building food database from CSV..."
python scripts/build_database.py \
    --csv ../data/daily_food_nutrition_dataset.csv \
    --db ../data/foods.db

echo "Starting application..."
exec "$@"
