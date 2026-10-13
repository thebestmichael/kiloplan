from sqlalchemy import func, select

from kiloplan.ingestion.usda import load_foods, read_foods
from kiloplan.storage.models import Food


def test_read_foods(usda_zip):
    chicken, rice, powder = read_foods(usda_zip)
    assert (chicken.fdc_id, chicken.name, chicken.category) == (
        1,
        "Chicken, breast, cooked",
        "Poultry Products",
    )
    assert chicken.kcal == 165
    # a portion with no gram weight is dropped
    assert chicken.portions == []
    # portions come back in the dataset's order, and other nutrients are ignored
    assert rice.portions == [("1 cup", 158.0), ("1 cup, packed", 186.0)]
    assert rice.nutrients == {1008: 130.0, 1003: 2.7, 1004: 0.3, 1005: 28.2, 1079: 0.4}
    # no energy value: 4 * 80 + 4 * 5 + 9 * 4
    assert (powder.category, powder.kcal) == ("", 376)


def test_load_foods_updates_rather_than_duplicates(usda_zip, session):
    records = read_foods(usda_zip)
    assert load_foods(session, records) == 3
    records[1].nutrients[1008] = 131
    load_foods(session, records)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Food)) == 3
    rice = session.scalar(select(Food).where(Food.fdc_id == 2))
    assert (rice.kcal, rice.fiber_g, len(rice.portions)) == (131, 0.4, 2)
