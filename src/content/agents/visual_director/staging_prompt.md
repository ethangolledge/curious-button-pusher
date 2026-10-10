# Staging scenes in 3D

This channel can build scenes as 3D shots: a set, the things in it, what they do, the light and a camera move, put together by code from a catalogue (`staging_catalogue`). A staged scene is rendered, not drawn, so it can move for real: the camera travels, things fall, cars drive. Everything else about a scene stays as above: its anchor, focus, motion, bridge and references are still required, and the morph into the next scene, the colour and the breathing are added the same way.

## When to stage a scene

Stage a scene when the catalogue can show its anchor plainly: a layout for its setting, a model for each key object, an action for what moves, a camera move. Leave `staging` empty and say in `missing` what the toolkit lacks, in a few words naming the kind and the thing ("layout: harbour at night", "model: oil tanker", "action: crowd surging"), when:

- the anchor is a person or people (unless the models list a model of them): people stay drawn;
- no layout fits the setting, or no model fits a key object;
- what must happen has no action.

A scene left unstaged is drawn as a keyframe, as before; `missing` is how the toolkit learns what to build next. Never force a poor fit.

## How to stage it

`staging` has a `layout`, `actors`, `actions`, `lights` and a `camera`, each a block from the catalogue by its exact name with only the `settings` that differ from the defaults (each a `name` and a text `value`).

- **layout**: the setting. Its description lists the marks (places) and paths (routes) it offers, and the actors it already places (an office's desk, chair and lamp): refer to those by name.
- **actors**: what you add, each with an `actor_id` you choose, an actor block (`prop` stands a model on a mark) and a `model` id from the models list. Refer to actors by their `actor_id` everywhere else.
- **actions**: what happens over the scene, in order. Their `start` and `end` are fractions of the scene's length.
- **lights**: one to three, matching the anchor's `light_and_colour`: a practical lamp, a window, overhead, or outdoor sky; at night, the sources in the scene.
- **camera**: one move, usually the theme move named in the scene's `camera` (the catalogue lists the theme's moves with the move blocks), with its `subject`: the anchor's actor, or the layout's actor that carries the scene.

Every name a setting refers to must exist in the shot: a mark or path the layout offers, an actor the layout places, or an actor you added. Numbers stay within the ranges given.

## Example

A scene whose anchor is a telephone on a desk in a dark office, the camera pushing in:

```json
{"layout": {"block": "office", "settings": [{"name": "blinds", "value": "yes"}]},
 "actors": [{"actor_id": "phone", "block": "prop", "model": "telephone",
             "settings": [{"name": "at", "value": "desk_top"}, {"name": "across", "value": "0.3"}]}],
 "actions": [],
 "lights": [{"block": "lamp", "settings": [{"name": "at", "value": "desk_lamp"}]},
            {"block": "window", "settings": [{"name": "time", "value": "night"}]}],
 "camera": {"block": "push_in", "settings": [{"name": "subject", "value": "phone"}, {"name": "framing", "value": "close"}]}}
```
