"""Builds a shot from a job, in the one order every shot is built: the layout, then the actors
(and the groups they are named in), then what they do, then the light, then the camera
(which may follow what moved). The same code runs inside Blender for a render and outside it
for a rehearsal."""

from content.blender.api import Stage
from content.blender.blocks.base import Action, Actor, Layout, Light, Move, read
from content.blender.job import Job
from content.blender.registry import Registry


def build(stage: Stage, job: Job, registry: Registry) -> None:
    layout = registry.get("layouts", job.layout.block)
    assert issubclass(layout, Layout)
    layout().build(stage, read(layout, job.layout.settings))
    for call in job.actors:
        actor = registry.get("actors", call.block)
        assert issubclass(actor, Actor)
        actor().build(stage, read(actor, call.settings), call.actor_id, call.model)
    for name, members in job.groups.items():
        # An empty at the origin with the members hung from it: where they are is unchanged,
        # and its extent is all of theirs.
        group = stage.group(name)
        for member in members:
            thing = stage.actor(member)
            stage.place(thing, stage.poses(thing)[0].at, parent=group)
        stage.cast(name, group)
    for action_call in job.actions:
        action = registry.get("actions", action_call.block)
        assert issubclass(action, Action)
        action().build(stage, read(action, action_call.settings))
    for light_call in job.lights:
        light = registry.get("lights", light_call.block)
        assert issubclass(light, Light)
        light().build(stage, read(light, light_call.settings))
    move = registry.get("moves", job.camera.block)
    assert issubclass(move, Move)
    move().build(stage, read(move, job.camera.settings))
