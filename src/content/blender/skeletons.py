"""The skeletons recorded motion comes on, and where each of a pose's joints is in each: one
table per family of skeleton, so any rigged character or recording of that family gives a pose
(`blender/poses.py`). A joint is where its bone starts (`LeftForeArm` starts at the elbow).

Plain Python: the names are matched without Blender."""

import re

# Each family: the bone each joint starts, by its plain name (`plain`), `{side}` filled with
# the family's word for a side; "top" is the top of the head, where the family has a bone for
# it (otherwise the head bone's end).
FAMILIES: dict[str, dict[str, object]] = {
    # Mixamo's, and CMU's in its BVH conversion: the same names.
    "mixamo": {
        "sides": {"L": "left", "R": "right"},
        "bones": {
            "neck": "neck", "head": "head", "top": "headtop_end",
            "shoulder": "{side}arm", "elbow": "{side}forearm", "wrist": "{side}hand",
            "hip": "{side}upleg", "knee": "{side}leg", "ankle": "{side}foot",
        },
    },
    "100style": {
        "sides": {"L": "left", "R": "right"},
        "bones": {
            "neck": "neck", "head": "head",
            "shoulder": "{side}shoulder", "elbow": "{side}elbow", "wrist": "{side}wrist",
            "hip": "{side}hip", "knee": "{side}knee", "ankle": "{side}ankle",
        },
    },
    # Renderpeople's scanned people.
    "renderpeople": {
        "sides": {"L": "l", "R": "r"},
        "bones": {
            "neck": "neck", "head": "head", "top": "head_end",
            "shoulder": "upperarm_{side}", "elbow": "lowerarm_{side}", "wrist": "hand_{side}",
            "hip": "upperleg_{side}", "knee": "lowerleg_{side}", "ankle": "foot_{side}",
        },
    },
    # Unreal's (many game characters).
    "unreal": {
        "sides": {"L": "l", "R": "r"},
        "bones": {
            "neck": "neck_01", "head": "head",
            "shoulder": "upperarm_{side}", "elbow": "lowerarm_{side}", "wrist": "hand_{side}",
            "hip": "thigh_{side}", "knee": "calf_{side}", "ankle": "foot_{side}",
        },
    },
}  # fmt: skip
# The joints a family gives by side.
LIMBS = ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")


def plain(name: str) -> str:
    """A bone's name without what tools add to it: Mixamo's `mixamorig:` prefix, Sketchfab's
    trailing number (`LeftArm_011`), case."""
    name = re.sub(r"^mixamorig\d*:", "", name)
    name = re.sub(r"_\d+$", "", name)
    return name.lower()


def matched(bones: list[str]) -> tuple[str, dict[str, str]] | None:
    """The family a skeleton's bones belong to, and the bone for each joint ("neck", "head",
    "top" if it has one, "elbow.L"…); None when no family has them all. A bone may carry a
    character's own prefix (`rp_nathan_..._upperarm_l`)."""
    by_plain = {plain(bone): bone for bone in bones}

    def find(wanted: str) -> str | None:
        if wanted in by_plain:
            return by_plain[wanted]
        return next((b for p, b in by_plain.items() if p.endswith(f"_{wanted}")), None)

    for family, table in FAMILIES.items():
        sides = table["sides"]
        names = table["bones"]
        assert isinstance(sides, dict) and isinstance(names, dict)
        found: dict[str, str] = {}
        for joint, wanted in names.items():
            if joint in LIMBS:
                for side, word in sides.items():
                    bone = find(wanted.format(side=word))
                    if bone is not None:
                        found[f"{joint}.{side}"] = bone
            elif (bone := find(wanted)) is not None:
                found[joint] = bone
        needed = {"neck", "head", *(f"{j}.{s}" for j in LIMBS for s in sides)}
        if needed <= found.keys():
            return family, found
    return None
