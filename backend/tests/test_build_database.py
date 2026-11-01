import os
import sqlite3
import subprocess
import sys
import tempfile
import pytest

from scripts.build_database import clean_and_load_data, validate_dataframe, create_sqlite_database
from app.config import DATA_DIR, DB_PATH


def test_build_database_results():
    csv_path = DATA_DIR / "daily_food_nutrition_dataset.csv"
    assert csv_path.exists(), f"Dataset CSV missing at {csv_path}"

    df = clean_and_load_data(str(csv_path))
    assert len(df) == 597

    # No null values
    assert df.isnull().sum().sum() == 0

    # No negative numbers
    num_cols = [
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "sugars_g",
        "sodium_mg",
        "cholesterol_mg",
    ]
    for col in num_cols:
        assert (df[col] < 0).sum() == 0

    # Specific comma rows exist
    expected_names = [
        "Milk (2%, 1 cup)",
        "Tea (Green, 1 cup)",
        "Spinach (1 cup, raw)",
    ]
    for name in expected_names:
        assert (df["name"] == name).any(), f"Expected name {name} not found"

    validate_dataframe(df)


def test_idempotent_build():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        tmp_db_path = tmp_db.name

    try:
        csv_path = str(DATA_DIR / "daily_food_nutrition_dataset.csv")
        df = clean_and_load_data(csv_path)

        create_sqlite_database(df, tmp_db_path)
        conn = sqlite3.connect(tmp_db_path)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM foods")
        count1 = cur.fetchone()[0]
        conn.close()

        # Run second time
        create_sqlite_database(df, tmp_db_path)
        conn = sqlite3.connect(tmp_db_path)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM foods")
        count2 = cur.fetchone()[0]
        conn.close()

        assert count1 == 597
        assert count2 == 597
    finally:
        if os.path.exists(tmp_db_path):
            os.remove(tmp_db_path)


def test_broken_csv_causes_exit():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp_csv:
        tmp_csv.write("Header1,Header2\nBadRow1\n")
        tmp_csv_path = tmp_csv.name

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        tmp_db_path = tmp_db.name

    try:
        cmd = [
            sys.executable,
            "scripts/build_database.py",
            "--csv",
            tmp_csv_path,
            "--db",
            tmp_db_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode != 0
    finally:
        if os.path.exists(tmp_csv_path):
            os.remove(tmp_csv_path)
        if os.path.exists(tmp_db_path):
            os.remove(tmp_db_path)
