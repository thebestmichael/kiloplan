import pytest

from kiloplan.analytics.plates import bar_total, load_bar

KG_PLATES = {25: 8, 20: 1, 15: 1, 10: 1, 5: 1, 2.5: 1, 1.25: 1}
LB_PLATES = {45: 8, 35: 1, 25: 1, 10: 2, 5: 1, 2.5: 1}


@pytest.mark.parametrize(
    ("target", "per_side"),
    [
        (20, ()),
        (60, (20,)),
        (100, (25, 15)),
        (140, (25, 25, 10)),
        (182.5, (25, 25, 25, 5, 1.25)),
        (227.5, (25, 25, 25, 25, 2.5, 1.25)),
    ],
)
def test_load_bar_in_kg(target, per_side):
    load = load_bar(target, bar=20, plates=KG_PLATES)
    assert (load.per_side, load.total, load.shortfall) == (per_side, target, 0)


@pytest.mark.parametrize(
    ("target", "per_side"),
    [(45, ()), (135, (45,)), (225, (45, 45)), (315, (45, 45, 45)), (405, (45, 45, 45, 45))],
)
def test_load_bar_in_lb(target, per_side):
    assert load_bar(target, bar=45, plates=LB_PLATES).per_side == per_side


def test_load_bar_stops_under_a_target_it_cannot_hit():
    load = load_bar(101, bar=20, plates=KG_PLATES)
    assert (load.per_side, load.total) == ((25, 15), 100)
    assert load.shortfall == pytest.approx(1)


def test_load_bar_counts_collars():
    load = load_bar(100, bar=20, plates=KG_PLATES, collar=2.5)
    assert (load.per_side, load.total) == ((25, 10, 2.5), 100)


def test_load_bar_respects_how_many_pairs_there_are():
    # one pair of 25s: the rest has to come from smaller plates
    load = load_bar(140, bar=20, plates={25: 1, 20: 1, 10: 1, 5: 1})
    assert (load.per_side, load.total) == ((25, 20, 10, 5), 140)

    short = load_bar(200, bar=20, plates={25: 1, 20: 1})
    assert (short.per_side, short.total, short.shortfall) == ((25, 20), 110, 90)


def test_load_bar_finds_a_load_greedy_picking_would_miss():
    # taking the 20 first leaves 4 unreachable; two 12s hit the target exactly
    load = load_bar(68, bar=20, plates={20: 1, 12: 2})
    assert (load.per_side, load.total) == ((12, 12), 68)


def test_load_bar_prefers_fewer_plates():
    assert load_bar(70, bar=20, plates={25: 1, 20: 1, 5: 5}).per_side == (25,)


def test_load_bar_with_no_plates_is_the_empty_bar():
    load = load_bar(60, bar=20, plates={})
    assert (load.per_side, load.total, load.shortfall) == ((), 20, 40)


@pytest.mark.parametrize(
    ("target", "bar", "plates", "collar"),
    [
        (15, 20, KG_PLATES, 0),
        (24, 20, KG_PLATES, 2.5),
        (60, -20, KG_PLATES, 0),
        (60, 20, {-5: 1}, 0),
    ],
)
def test_load_bar_rejects_impossible_input(target, bar, plates, collar):
    with pytest.raises(ValueError):
        load_bar(target, bar=bar, plates=plates, collar=collar)


def test_bar_total_is_the_reverse_of_load_bar():
    assert bar_total([25, 25, 25, 5, 1.25], bar=20) == 182.5
    assert bar_total([45, 45, 25], bar=45) == 275
    assert bar_total([25, 10, 2.5], bar=20, collar=2.5) == 100
    assert bar_total([], bar=20) == 20
    with pytest.raises(ValueError):
        bar_total([25, -5], bar=20)
