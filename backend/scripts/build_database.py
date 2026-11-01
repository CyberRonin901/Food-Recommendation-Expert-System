#!/usr/bin/env python3
import argparse
import csv
import os
import re
import sqlite3
import sys
import unicodedata
import pandas as pd


def make_name_search(name: str) -> str:
    """
    Transforms food name into a search string:
    lowercase, accents removed, punctuation replaced by spaces, padded with single spaces.
    e.g. "Bun (hamburger)" -> " bun hamburger "
    """
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_text = nfkd.encode("ASCII", "ignore").decode("utf-8").lower()
    clean_text = re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()
    return f" {' '.join(clean_text.split())} "


def clean_and_load_data(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    cleaned_rows = []
    header = None

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for line_no, row in enumerate(reader, start=1):
            if not row:
                continue
            if header is None:
                header = [c.strip() for c in row]
                continue

            # Problem 1: Unquoted comma in food name causes 13 columns instead of 12
            if len(row) == 13:
                row = [row[0] + "," + row[1]] + row[2:]
            elif len(row) != 12:
                print(f"Warning: line {line_no} has {len(row)} columns, skipping: {row}", file=sys.stderr)
                continue

            cleaned_rows.append(row)

    if not header or len(header) != 12:
        raise ValueError(f"Invalid CSV header: {header}")

    # Column mapping from CSV to DataFrame
    col_names = [
        "name",
        "category",
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "sugars_g",
        "sodium_mg",
        "cholesterol_mg",
        "meal_type",
        "water_ml",
    ]

    df = pd.DataFrame(cleaned_rows, columns=col_names)

    # Problem 2: Exact duplicate rows
    initial_count = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    deduped_count = len(df)
    print(f"Read {initial_count} rows, dropped {initial_count - deduped_count} duplicates -> {deduped_count} rows")

    # Numeric conversion
    num_cols = [
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "sugars_g",
        "sodium_mg",
        "cholesterol_mg",
        "water_ml",
    ]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # String cleaning
    df["name"] = df["name"].astype(str).str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    df["meal_type"] = df["meal_type"].astype(str).str.strip()

    # Problem 4: Split compound category
    def split_category(cat: str):
        if "/" in cat:
            parts = cat.split("/", 1)
            return parts[0].strip(), parts[1].strip()
        return cat.strip(), ""

    cats = df["category"].apply(split_category)
    df["category_main"] = [c[0] for c in cats]
    df["category_sub"] = [c[1] for c in cats]

    # Problem 9: name_search for word matching
    df["name_search"] = df["name"].apply(make_name_search)

    # Calculate percentiles: pct = (rank_min(value) - 1) / (N - 1)
    N = len(df)
    rank_nutrients = [
        ("calories", "pct_calories"),
        ("protein_g", "pct_protein"),
        ("carbs_g", "pct_carbs"),
        ("fat_g", "pct_fat"),
        ("fiber_g", "pct_fiber"),
        ("sugars_g", "pct_sugars"),
        ("sodium_mg", "pct_sodium"),
        ("cholesterol_mg", "pct_cholesterol"),
    ]
    for raw_col, pct_col in rank_nutrients:
        ranks = df[raw_col].rank(method="min")
        df[pct_col] = (ranks - 1.0) / (N - 1.0)

    return df


def validate_dataframe(df: pd.DataFrame) -> None:
    errors = []

    # 1. Row count must be exactly 597
    if len(df) != 597:
        errors.append(f"Expected exactly 597 rows, found {len(df)}")

    # 2. No null values
    null_counts = df.isnull().sum()
    if null_counts.sum() > 0:
        errors.append(f"Found null values in dataframe: {null_counts[null_counts > 0].to_dict()}")

    # 3. No negative numbers in nutrient columns
    num_cols = [
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "sugars_g",
        "sodium_mg",
        "cholesterol_mg",
        "water_ml",
    ]
    for col in num_cols:
        negatives = (df[col] < 0).sum()
        if negatives > 0:
            errors.append(f"Found {negatives} negative values in column {col}")

    # 4. Check that specific comma rows exist
    expected_names = [
        "Milk (2%, 1 cup)",
        "Tea (Green, 1 cup)",
        "Spinach (1 cup, raw)",
    ]
    for name in expected_names:
        if not (df["name"] == name).any():
            errors.append(f"Expected comma row missing: '{name}'")

    if errors:
        for err in errors:
            print(f"VALIDATION ERROR: {err}", file=sys.stderr)
        raise ValueError(f"Data validation failed with {len(errors)} error(s).")

    print("Data validation passed successfully: 597 rows, 0 nulls, 0 negatives, all sanity checks OK.")


def create_sqlite_database(df: pd.DataFrame, db_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS foods")
    cur.execute(
        """
        CREATE TABLE foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_search TEXT NOT NULL,
            category TEXT NOT NULL,
            category_main TEXT NOT NULL,
            category_sub TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            calories REAL NOT NULL,
            protein_g REAL NOT NULL,
            carbs_g REAL NOT NULL,
            fat_g REAL NOT NULL,
            fiber_g REAL NOT NULL,
            sugars_g REAL NOT NULL,
            sodium_mg REAL NOT NULL,
            cholesterol_mg REAL NOT NULL,
            water_ml REAL NOT NULL,
            pct_calories REAL NOT NULL,
            pct_protein REAL NOT NULL,
            pct_carbs REAL NOT NULL,
            pct_fat REAL NOT NULL,
            pct_fiber REAL NOT NULL,
            pct_sugars REAL NOT NULL,
            pct_sodium REAL NOT NULL,
            pct_cholesterol REAL NOT NULL
        )
        """
    )

    insert_cols = [
        "name",
        "name_search",
        "category",
        "category_main",
        "category_sub",
        "meal_type",
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "sugars_g",
        "sodium_mg",
        "cholesterol_mg",
        "water_ml",
        "pct_calories",
        "pct_protein",
        "pct_carbs",
        "pct_fat",
        "pct_fiber",
        "pct_sugars",
        "pct_sodium",
        "pct_cholesterol",
    ]

    placeholders = ", ".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO foods ({', '.join(insert_cols)}) VALUES ({placeholders})"

    rows_to_insert = [tuple(x) for x in df[insert_cols].to_numpy()]
    cur.executemany(sql, rows_to_insert)

    cur.execute("CREATE INDEX idx_foods_meal_type ON foods(meal_type)")
    cur.execute("CREATE INDEX idx_foods_category_main ON foods(category_main)")
    cur.execute("CREATE INDEX idx_foods_calories ON foods(calories)")
    cur.execute("CREATE INDEX idx_foods_protein ON foods(protein_g)")

    conn.commit()

    # Verification query
    cur.execute("SELECT count(*) FROM foods")
    count = cur.fetchone()[0]
    conn.close()

    if count != 597:
        raise ValueError(f"SQLite verification failed: table has {count} rows instead of 597")

    print(f"Successfully created database at {db_path} with {count} rows.")


def main():
    parser = argparse.ArgumentParser(description="Clean CSV and build foods SQLite database")
    parser.add_argument("--csv", required=True, help="Path to input CSV")
    parser.add_argument("--db", required=True, help="Path to output SQLite database")
    args = parser.parse_args()

    try:
        df = clean_and_load_data(args.csv)
        validate_dataframe(df)
        create_sqlite_database(df, args.db)
    except Exception as e:
        print(f"Error building database: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

