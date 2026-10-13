"""A tiny USDA FoodData Central archive for tests."""

import zipfile
from pathlib import Path

FOOD_CSV = """fdc_id,data_type,description,food_category_id,publication_date
1,sr_legacy_food,"Chicken, breast, cooked",5,2019-04-01
2,sr_legacy_food,"Rice, white, cooked",20,2019-04-01
3,sr_legacy_food,Mystery powder,99,2019-04-01
"""

NUTRIENT_CSV = """id,fdc_id,nutrient_id,amount
1,1,1008,165
2,1,1003,31
3,1,1004,3.6
4,1,1005,0
5,2,1008,130
6,2,1003,2.7
7,2,1004,0.3
8,2,1005,28.2
9,2,1079,0.4
10,2,1093,1
11,3,1003,80
12,3,1005,5
13,3,1004,4
"""

PORTION_CSV = """id,fdc_id,seq_num,amount,measure_unit_id,portion_description,modifier,gram_weight
1,2,2,1,9999,,"cup, packed",186
2,2,1,1,9999,,cup,158
3,1,1,1,9999,,breast,0
"""

CATEGORY_CSV = """id,code,description
5,0500,Poultry Products
20,2000,Cereal Grains and Pasta
"""


def write_usda_zip(path: Path) -> Path:
    """Write the archive in the layout the real download uses: one folder of CSV files."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in (
            ("food.csv", FOOD_CSV),
            ("food_nutrient.csv", NUTRIENT_CSV),
            ("food_portion.csv", PORTION_CSV),
            ("food_category.csv", CATEGORY_CSV),
        ):
            archive.writestr(f"dataset/{name}", content)
    return path
