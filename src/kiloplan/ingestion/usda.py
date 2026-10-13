"""Loads USDA FoodData Central's SR Legacy foods into the app database.

Run with: uv run python -m kiloplan.ingestion.usda
The dataset is public domain: about 7,800 generic foods with nutrients per 100 g.
"""

import csv
import io
import urllib.request
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from kiloplan.analytics.nutrition import kcal_from_macros
from kiloplan.storage.db import get_engine
from kiloplan.storage.models import Food, FoodPortion

SR_LEGACY_URL = (
    "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
)
DEFAULT_ZIP = Path("data/usda/sr_legacy.zip")

# FoodData Central nutrient ids
ENERGY_KCAL, PROTEIN, FAT, CARBS, FIBER = 1008, 1003, 1004, 1005, 1079
NUTRIENTS = {ENERGY_KCAL, PROTEIN, FAT, CARBS, FIBER}


@dataclass
class FoodRecord:
    """A food with nutrients per 100 g and its household portions as (description, grams)."""

    fdc_id: int
    name: str
    category: str
    nutrients: dict[int, float] = field(default_factory=dict)
    portions: list[tuple[str, float]] = field(default_factory=list)

    @property
    def kcal(self) -> float:
        if ENERGY_KCAL in self.nutrients:
            return self.nutrients[ENERGY_KCAL]
        return kcal_from_macros(
            self.nutrients.get(PROTEIN, 0.0),
            self.nutrients.get(CARBS, 0.0),
            self.nutrients.get(FAT, 0.0),
        )


def _rows(archive: zipfile.ZipFile, filename: str) -> Iterator[dict[str, str]]:
    member = next(name for name in archive.namelist() if name.endswith(f"/{filename}"))
    with archive.open(member) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, "utf-8"))


def read_foods(zip_path: str | Path) -> list[FoodRecord]:
    """Read every food in a FoodData Central CSV archive."""
    with zipfile.ZipFile(zip_path) as archive:
        categories = {row["id"]: row["description"] for row in _rows(archive, "food_category.csv")}
        foods = {
            int(row["fdc_id"]): FoodRecord(
                fdc_id=int(row["fdc_id"]),
                name=row["description"].strip(),
                category=categories.get(row["food_category_id"], ""),
            )
            for row in _rows(archive, "food.csv")
        }
        for row in _rows(archive, "food_nutrient.csv"):
            nutrient = int(row["nutrient_id"])
            food = foods.get(int(row["fdc_id"]))
            if food and nutrient in NUTRIENTS and row["amount"]:
                food.nutrients[nutrient] = float(row["amount"])
        portions: dict[int, list[tuple[int, str, float]]] = defaultdict(list)
        for row in _rows(archive, "food_portion.csv"):
            if not row["gram_weight"] or float(row["gram_weight"]) <= 0:
                continue
            amount = f"{float(row['amount']):g}" if row["amount"] else ""
            description = " ".join(part for part in (amount, row["modifier"].strip()) if part)
            sequence = int(row["seq_num"] or 0)
            portions[int(row["fdc_id"])].append((sequence, description, float(row["gram_weight"])))
        for fdc_id, listed in portions.items():
            if fdc_id in foods:
                foods[fdc_id].portions = [(text, grams) for _, text, grams in sorted(listed)]
    return list(foods.values())


def load_foods(session: Session, records: list[FoodRecord]) -> int:
    """Insert or update USDA foods by their FDC id. Returns how many were written."""
    existing = {
        food.fdc_id: food for food in session.scalars(select(Food).where(Food.source == "usda"))
    }
    for record in records:
        food = existing.get(record.fdc_id)
        if food is None:
            food = Food(source="usda", fdc_id=record.fdc_id)
            session.add(food)
        food.name = record.name
        food.category = record.category
        food.kcal = record.kcal
        food.protein_g = record.nutrients.get(PROTEIN, 0.0)
        food.carbs_g = record.nutrients.get(CARBS, 0.0)
        food.fat_g = record.nutrients.get(FAT, 0.0)
        food.fiber_g = record.nutrients.get(FIBER, 0.0)
        food.portions = [
            FoodPortion(description=description, grams=grams)
            for description, grams in record.portions
        ]
    session.flush()
    return len(records)


def download(destination: Path = DEFAULT_ZIP) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(SR_LEGACY_URL, destination)  # noqa: S310
    return destination


def main() -> None:
    zip_path = DEFAULT_ZIP if DEFAULT_ZIP.exists() else download()
    records = read_foods(zip_path)
    with Session(get_engine()) as session:
        count = load_foods(session, records)
        session.commit()
    print(f"Loaded {count} USDA foods from {zip_path}")


if __name__ == "__main__":
    main()
