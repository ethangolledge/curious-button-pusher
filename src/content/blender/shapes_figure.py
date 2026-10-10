"""A stylised figurine made of simple solids, standing or seated: the shape every made-in-code
person shares. Simple on purpose: under the channel's look it reads as a drawn or carved
figure, never a failed attempt at a real one."""

from typing import Literal

from content.blender.api import Stage, Thing
from content.blender.maths import Vec

HEIGHT = 1.75


def figurine(stage: Stage, name: str, pose: Literal["standing", "seated"]) -> Thing:
    body = stage.group(name)
    seated = pose == "seated"
    hip = 0.47 if seated else 0.92
    # Legs: straight down standing; seated, thighs forward and shins down to the floor.
    for side in (-1, 1):
        x = side * 0.1
        if seated:
            stage.shape(
                "cylinder",
                Vec(0.15, 0.15, 0.45),
                Vec(x, 0.0, hip),
                role="fabric",
                name=f"{name}.thigh_{side + 1}",
                turn=Vec(90, 0, 0),
                parent=body,
            )  # noqa: E501
            stage.shape(
                "cylinder",
                Vec(0.12, 0.12, hip - 0.05),
                Vec(x, -0.42, 0.05),
                role="fabric",
                name=f"{name}.shin_{side + 1}",
                parent=body,
            )  # noqa: E501
            stage.shape(
                "box",
                Vec(0.11, 0.26, 0.07),
                Vec(x, -0.48, 0.0),
                role="leather",
                name=f"{name}.shoe_{side + 1}",
                parent=body,
                bevel=0.02,
            )  # noqa: E501
        else:
            stage.shape(
                "cylinder",
                Vec(0.14, 0.14, hip - 0.05),
                Vec(x, 0.0, 0.05),
                role="fabric",
                name=f"{name}.leg_{side + 1}",
                parent=body,
            )  # noqa: E501
            stage.shape(
                "box",
                Vec(0.11, 0.26, 0.07),
                Vec(x, -0.05, 0.0),
                role="leather",
                name=f"{name}.shoe_{side + 1}",
                parent=body,
                bevel=0.02,
            )  # noqa: E501
    stage.shape(
        "box",
        Vec(0.36, 0.22, 0.16),
        Vec(0, 0, hip - 0.04),
        role="fabric",
        name=f"{name}.hips",
        parent=body,
        bevel=0.05,
    )  # noqa: E501
    stage.shape(
        "box",
        Vec(0.42, 0.24, 0.56),
        Vec(0, 0, hip + 0.1),
        role="fabric",
        name=f"{name}.torso",
        parent=body,
        bevel=0.07,
    )  # noqa: E501
    shoulder = hip + 0.62
    for side in (-1, 1):
        if seated:
            # Forearms rest forward, as on a table.
            stage.shape(
                "cylinder",
                Vec(0.1, 0.1, 0.3),
                Vec(side * 0.25, 0.0, shoulder - 0.3),
                role="fabric",
                name=f"{name}.upper_arm_{side + 1}",
                parent=body,
            )  # noqa: E501
            stage.shape(
                "cylinder",
                Vec(0.09, 0.09, 0.32),
                Vec(side * 0.22, 0.0, shoulder - 0.3),
                role="fabric",
                name=f"{name}.forearm_{side + 1}",
                turn=Vec(90, 0, 0),
                parent=body,
            )  # noqa: E501
            stage.shape(
                "sphere",
                Vec(0.09, 0.1, 0.07),
                Vec(side * 0.22, -0.34, shoulder - 0.34),
                role="skin",
                name=f"{name}.hand_{side + 1}",
                parent=body,
            )  # noqa: E501
        else:
            stage.shape(
                "cylinder",
                Vec(0.1, 0.1, 0.62),
                Vec(side * 0.26, 0.0, shoulder - 0.62),
                role="fabric",
                name=f"{name}.arm_{side + 1}",
                parent=body,
                turn=Vec(0, side * 4, 0),
            )  # noqa: E501
            stage.shape(
                "sphere",
                Vec(0.09, 0.07, 0.11),
                Vec(side * 0.28, 0.0, shoulder - 0.72),
                role="skin",
                name=f"{name}.hand_{side + 1}",
                parent=body,
            )  # noqa: E501
    stage.shape(
        "cylinder",
        Vec(0.1, 0.1, 0.1),
        Vec(0, 0, shoulder - 0.02),
        role="skin",
        name=f"{name}.neck",
        parent=body,
    )  # noqa: E501
    stage.shape(
        "sphere",
        Vec(0.2, 0.23, 0.25),
        Vec(0, -0.01, shoulder + 0.06),
        role="skin",
        name=f"{name}.head",
        parent=body,
    )  # noqa: E501
    stage.shape(
        "sphere",
        Vec(0.21, 0.23, 0.13),
        Vec(0, 0.015, shoulder + 0.2),
        role="hair",
        name=f"{name}.hair",
        parent=body,
    )  # noqa: E501
    return body
