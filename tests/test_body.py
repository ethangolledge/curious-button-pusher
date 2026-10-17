"""How a person is posed, as rules (`blender/body.py`): the same for everyone, wherever they
are and whichever way they face, measured on the real table before them."""

import pytest

from content.blender.api import Box
from content.blender.body import (
    RESTING_HAND,
    SEAT_REACH,
    TABLE_HEIGHT,
    Frame,
    holds,
    reaches,
    table_before,
    ways,
)
from content.blender.maths import UP, Quat, Vec, axis_angle

SEATED = Frame(hips=Vec(0.0, 0.0, 0.5), floor=0.0, turn=Quat())


def test_a_table_is_measured_from_its_nearest_edge_along_the_way_they_face() -> None:
    desk = Box(Vec(-0.75, -1.1, 0.0), Vec(0.75, -0.4, 0.76))

    table = table_before(desk, SEATED)

    assert table.near == pytest.approx(0.4) and table.top == pytest.approx(0.76)


def test_hands_rest_on_the_real_table_whatever_its_height_and_distance() -> None:
    near, far = (Box(Vec(-0.75, -y - 0.7, 0.0), Vec(0.75, -y, top)) for y, top in
                 ((0.3, 0.72), (0.45, 0.8)))  # fmt: skip

    on_near = reaches("seated", "resting", SEATED, table_before(near, SEATED))
    on_far = reaches("seated", "resting", SEATED, table_before(far, SEATED))

    for hand_near, hand_far in zip(on_near, on_far, strict=True):
        # Further back by the table's extra distance, higher by its extra height.
        assert hand_near.at.y - hand_far.at.y == pytest.approx(0.15)
        assert hand_far.at.z - hand_near.at.z == pytest.approx(0.08)
        assert hand_far.lying == RESTING_HAND and hand_far.surface == pytest.approx(0.8)


def test_without_a_table_hands_go_to_the_table_a_person_is_made_for() -> None:
    hands = reaches("seated", "resting", SEATED, None)

    assert all(hand.surface == pytest.approx(TABLE_HEIGHT) for hand in hands)
    assert all(hand.at.y < -SEAT_REACH for hand in hands)


def test_a_person_turned_is_posed_turned() -> None:
    turned = Frame(SEATED.hips, 0.0, axis_angle(UP, 90.0))

    straight = holds("seated", "drink", SEATED, None)["drink"]
    round_ = holds("seated", "drink", turned, None)["drink"]
    limbs, turned_limbs = ways("seated", SEATED), ways("seated", turned)

    assert round_.z == pytest.approx(straight.z)
    assert axis_angle(UP, 90.0).rotate(straight).x == pytest.approx(round_.x)
    assert axis_angle(UP, 90.0).rotate(limbs["upperleg01.L"]).y == pytest.approx(
        turned_limbs["upperleg01.L"].y
    )


def test_a_taller_person_reaches_further_from_their_hips_but_not_into_the_table() -> None:
    tall = Frame(SEATED.hips, 0.0, Quat(), scale=1.2)

    pocket, tall_pocket = (reaches("standing", "pockets", f, None)[0] for f in (SEATED, tall))
    on_table, tall_on_table = (reaches("seated", "resting", f, None)[0] for f in (SEATED, tall))

    assert abs(tall_pocket.at.x) == pytest.approx(abs(pocket.at.x) * 1.2)
    assert tall_on_table.at.z == pytest.approx(on_table.at.z)  # the table's top is the table's
