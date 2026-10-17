"""How a person is posed, as joints (`blender/body.py`): the same for everyone, wherever they
are and whichever way they face, fitted to the real seat and table before them; and the
skeletons recorded motion comes on, read by name (`blender/skeletons.py`)."""

from pathlib import Path

import pytest

from content.blender.api import Box, Figure
from content.blender.body import (
    ANKLE_HEIGHT,
    HIP_ABOVE_SEAT,
    SEAT_REACH,
    STANDING,
    TABLE_HEIGHT,
    Frame,
    holds,
    placed,
    reached,
    reaches,
    seated,
    table_before,
    two_bone,
)
from content.blender.maths import UP, Quat, Vec, axis_angle
from content.blender.skeletons import matched
from content.staging.poses import draw

STANDS = Figure({name: Vec(*point) for name, point in STANDING.items()})
SEATED = Frame(hips=Vec(0.0, 0.0, 0.5), floor=0.0, turn=Quat())


def _sitting() -> Figure:
    """A standing figure with its thighs run forward, as a recorded sitting pose has them."""
    joints = dict(STANDS.joints)
    for side, x in (("L", 0.1), ("R", -0.1)):
        joints[f"knee.{side}"] = Vec(x, -0.43, 0.94)
        joints[f"ankle.{side}"] = Vec(x, -0.45, 0.51)
    return Figure(joints)


def test_a_two_bone_limb_reaches_its_target_and_keeps_its_bones() -> None:
    root, middle, end = Vec(0, 0, 1), Vec(0, 0, 0.6), Vec(0, 0, 0.2)
    target, pole = Vec(0.3, -0.4, 0.5), Vec(0, -1, 0.6)

    bent, reached_end = two_bone(root, middle, end, target, pole)

    assert (reached_end - target).length() == pytest.approx(0.0, abs=1e-6)
    assert (bent - root).length() == pytest.approx(0.4)
    assert (reached_end - bent).length() == pytest.approx(0.4)
    assert bent.y < 0  # bent towards the pole, not away from it


def test_a_limb_too_short_to_reach_points_straight_at_it() -> None:
    root, middle, end = Vec(0, 0, 1), Vec(0, 0, 0.6), Vec(0, 0, 0.2)

    _, reached_end = two_bone(root, middle, end, Vec(0, -3, 1), Vec(0, -1, 0))

    assert (reached_end - root).length() == pytest.approx(0.8, abs=1e-5)
    assert reached_end.y < -0.79


def test_seated_the_hips_are_on_the_seat_and_the_feet_on_the_floor() -> None:
    turn = Quat()

    sat = seated(placed(_sitting(), Vec(1, 2, 0), turn, 1.0), 0.45, 0.0, turn, 1.0)

    assert sat.hips.z == pytest.approx(0.45 + HIP_ABOVE_SEAT)
    for side in "LR":
        assert sat.joints[f"ankle.{side}"].z == pytest.approx(ANKLE_HEIGHT, abs=1e-4)
        # The shin stands under its knee, the foot a little ahead (−Y).
        assert sat.joints[f"ankle.{side}"].y < sat.joints[f"knee.{side}"].y


def test_hands_rest_on_the_real_table_whatever_its_height_and_distance() -> None:
    near, far = (Box(Vec(-0.75, -y - 0.7, 0.0), Vec(0.75, -y, top)) for y, top in
                 ((0.3, 0.72), (0.45, 0.8)))  # fmt: skip

    on_near = reaches("seated", "resting", SEATED, table_before(near, SEATED))
    on_far = reaches("seated", "resting", SEATED, table_before(far, SEATED))

    for hand_near, hand_far in zip(on_near, on_far, strict=True):
        assert hand_near.at.y - hand_far.at.y == pytest.approx(0.15)
        assert hand_far.at.z - hand_near.at.z == pytest.approx(0.08)


def test_a_seated_figure_reaching_a_table_puts_its_wrists_there() -> None:
    turn = Quat()
    sat = seated(placed(_sitting(), Vec(), turn, 1.0), 0.45, 0.0, turn, 1.0)
    frame = Frame(sat.hips, 0.0, turn)
    desk = Box(Vec(-0.75, -0.9, 0.0), Vec(0.75, -0.35, 0.76))

    for hand in reaches("seated", "resting", frame, table_before(desk, frame)):
        sat = reached(sat, hand.side, hand.at, hand.elbow)
        assert (sat.joints[f"wrist.{hand.side}"] - hand.at).length() < 1e-3


def test_without_a_table_hands_go_to_the_usual_table() -> None:
    hands = reaches("seated", "resting", SEATED, None)

    assert all(hand.at.z == pytest.approx(TABLE_HEIGHT + 0.03) for hand in hands)
    assert all(hand.at.y < -SEAT_REACH for hand in hands)


def test_a_person_turned_is_posed_turned() -> None:
    turned = Frame(SEATED.hips, 0.0, axis_angle(UP, 90.0))

    straight = holds("seated", "drink", SEATED, None)["drink"]
    round_ = holds("seated", "drink", turned, None)["drink"]
    placed_turned = placed(STANDS, Vec(), axis_angle(UP, 90.0), 1.0)

    assert round_.z == pytest.approx(straight.z)
    assert axis_angle(UP, 90.0).rotate(straight).x == pytest.approx(round_.x)
    # Facing −Y the nose is in front; turned a quarter it points the turned way.
    assert placed_turned.joints["nose"].x == pytest.approx(0.1)


@pytest.mark.parametrize(
    ("bones", "family"),
    [
        (["mixamorig:LeftArm_011", "mixamorig:RightArm_035", "mixamorig:LeftForeArm_012",
          "mixamorig:RightForeArm_036", "mixamorig:LeftHand_013", "mixamorig:RightHand_037",
          "mixamorig:LeftUpLeg_062", "mixamorig:RightUpLeg_067", "mixamorig:LeftLeg_063",
          "mixamorig:RightLeg_068", "mixamorig:LeftFoot_064", "mixamorig:RightFoot_069",
          "mixamorig:Neck_05", "mixamorig:Head_06", "mixamorig:HeadTop_End_07"], "mixamo"),
        (["Neck", "Head", "LeftShoulder", "RightShoulder", "LeftElbow", "RightElbow",
          "LeftWrist", "RightWrist", "LeftHip", "RightHip", "LeftKnee", "RightKnee",
          "LeftAnkle", "RightAnkle"], "100style"),
        ([f"rp_nathan_walking_{b}_0{i}" for i, b in enumerate(
            ["neck", "head", "head_end", "upperarm_l", "upperarm_r", "lowerarm_l",
             "lowerarm_r", "hand_l", "hand_r", "upperleg_l", "upperleg_r", "lowerleg_l",
             "lowerleg_r", "foot_l", "foot_r"])], "renderpeople"),
    ],
)  # fmt: skip
def test_each_family_of_skeleton_gives_every_joint(bones: list[str], family: str) -> None:
    found = matched(bones)

    assert found is not None and found[0] == family
    assert {"neck", "head", "elbow.L", "ankle.R"} <= found[1].keys()


def test_a_skeleton_with_no_known_family_is_refused() -> None:
    assert matched(["Bone", "Bone.001", "spine"]) is None


def test_a_skeleton_is_drawn_where_its_joints_are_seen(tmp_path: Path) -> None:
    from PIL import Image

    picture = tmp_path / "layout.png"
    Image.new("RGB", (200, 400), (90, 90, 90)).save(picture)
    seen = {"man": {"neck": [100.0, 100.0, 3.0], "shoulder.R": [60.0, 110.0, 3.0]}}

    drawn = Image.open(draw(picture, seen, tmp_path / "posed.png"))

    assert drawn.getpixel((80, 105)) == (255, 0, 0)  # neck to right shoulder: OpenPose red
    assert drawn.getpixel((10, 10)) == (90, 90, 90)


def test_a_limb_hidden_behind_something_is_left_out(tmp_path: Path) -> None:
    from PIL import Image

    picture = tmp_path / "layout.png"
    Image.new("RGB", (200, 400), (90, 90, 90)).save(picture)
    seen = {"man": {"hip.R": [60.0, 200.0, 3.0, 1.0], "knee.R": [60.0, 300.0, 3.0, 0.0]}}

    drawn = Image.open(draw(picture, seen, tmp_path / "posed.png"))

    assert drawn.getpixel((60, 250)) == (90, 90, 90)  # the thigh runs behind the desk


def test_a_person_standing_at_ease_is_standing_and_natural() -> None:
    from content.staging.poses import judged

    judgement = judged(STANDS)

    assert judgement.kind == "standing" and judgement.plausible and judgement.faults == {}


def test_a_head_tilted_back_and_an_arm_raised_are_faults() -> None:
    from content.staging.poses import judged

    joints = dict(STANDS.joints)
    joints["nose"] = joints["nose"] + Vec(0.0, 0.0, 0.08)  # the chin up
    joints["wrist.R"] = Vec(-0.25, -0.1, 1.7)
    joints["elbow.R"] = Vec(-0.25, -0.05, 1.45)

    faults = judged(Figure(joints)).faults

    assert faults["looks up"] > 10 and faults["arms raised"] > 10


def test_a_sitting_figure_is_seated_and_a_broken_body_never_ranks() -> None:
    from content.staging.poses import judged

    sat = seated(placed(_sitting(), Vec(), Quat(), 1.0), 0.45, 0.0, Quat(), 1.0)
    stretched = Figure({**STANDS.joints, "ankle.L": Vec(0.1, 0.0, -0.9)})

    assert judged(sat).kind == "seated"
    assert not judged(stretched).plausible and judged(stretched).score == float("inf")


def test_arms_held_out_as_in_a_t_pose_are_a_fault() -> None:
    from content.staging.poses import judged

    joints = dict(STANDS.joints)
    for side, x in (("L", 1.0), ("R", -1.0)):
        shoulder = joints[f"shoulder.{side}"]
        joints[f"elbow.{side}"] = shoulder + Vec(0.28 * x, 0.0, 0.0)
        joints[f"wrist.{side}"] = shoulder + Vec(0.55 * x, 0.0, 0.0)

    assert judged(Figure(joints)).faults["arms out"] > 50
