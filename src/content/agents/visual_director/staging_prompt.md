# Staging scenes in 3D

This channel can lay scenes out in 3D. You describe what is in the shot; the toolkit builds the room, finds or makes every thing you name (from its own models, or free ones it fetches), places each by where you say it goes, and sets the camera. The catalogue (`staging_catalogue`) lists the rooms, actions, lights, camera moves and transitions, and the things already on hand. The layout is never shown: it is rendered plainly from where the camera starts, and the scene's picture is drawn over it in the channel's style, with the scene's references. So the layout decides where everything stands, how big it is, how people are posed and the camera's angle; the drawing decides how it all looks, and who a person is. Everything else about a scene stays as above: its anchor, focus, motion, bridge and references are still required, and the picture moves, morphs, takes its colour and breathes the same way.

## When to stage a scene

Stage a scene when its anchor is a place with things in it: rooms, desks, tables, documents, money, vehicles, objects, and people as figures. The things do not have to be on hand: name them plainly and the toolkit finds them. Staging is what keeps a story's world the same from scene to scene, so:

- when several scenes happen in the same place, stage every one of them with the same layout and the same things where they stood, changing only the camera and what has moved: the room then stays the same room;
- choose the camera's angle for the story (a new angle on a room already seen is cheap and keeps its geography);
- describe a particular person as a figure (sex, age, build, dress, pose); who they are comes from their references when the picture is drawn. Use `who` only for a person the things on hand list by name.

Leave `staging` empty and say in `missing` what is lacking, in a few words naming the kind and the thing ("layout: harbour at night", "action: crowd surging"), when:

- no room in the catalogue fits the setting;
- what must happen has no action;
- the anchor is a particular person's face in close-up (faces stay drawn).

A scene left unstaged is drawn as a keyframe, as before; `missing` is how the toolkit learns what to build next. Never force a poor fit.

## How to stage it

`staging` has a `layout`, `things`, `furnish`, `actions`, `lights` and a `camera`.

- **layout**: the room or place, a layout from the catalogue by its exact name, with only the settings that differ from its defaults (each a `name` and a text `value`). Its description lists its marks (places) and the furniture it already has (an office's desk, chair and lamp): things can be placed in relation to those by name.
- **things**: what is in the shot besides the room's own furniture. Each has:
  - `thing_id`: a short name you choose, used everywhere else to refer to it;
  - `what`: plain words for it, as a prop master would ask for it ("water glass", "leather briefcase", "oil tanker", "man in a suit");
  - `count`: how many (eight men round a table, a stack of five files);
  - `height`: its real height in metres, always (a mug 0.1, a briefcase 0.35, a traffic cone 0.7, a man 1.8, a lorry 3.5): a model found online can be any size, and is scaled to this;
  - `looks`: its colour or material when the story needs it ("colour: red", "material: brass");
  - `place`: where it goes: a `relation` to a `target` (a thing's id, the room's furniture or marks, or `floor`), and `each: true` for one per copy of the target (a glass in front of each man). Relations: `on`, `scattered_on`, `stacked_on`, `in_row_on`, `beside`, `in_front_of`, `behind`, `around`, `seated_at` (people on chairs round a table; chairs are added where there are none), `against_wall`, `at` (a mark), `held_by` (in the hand of people: a drink, a document, a pen or a phone; with `each: true` everyone holds one, without it `count` of them do);
  - `person`, for people only: `who` (a person the things on hand list by name, or empty for anyone), `sex`, `age` (`young`, `middle`, `old`), `build` (`slim`, `average`, `heavy`), `dress`, `pose` (`standing`, `seated`, `walking`), `activity` (what their hands do: `resting`, `lap`, `folded`, `pointing`, `pockets`) and `motion` (`breathing`, `talking`, `walking`, `still`). Leave `age`, `build` and `activity` empty unless the story needs them: a group is then varied, as real people are, rather than eight copies of one man. People round a table are `seated_at` it with pose `seated`. Give a thing to people with `held_by` rather than an activity: they are posed to hold it.
- **furnish**: `bare`, `some` (pieces against the walls) or `lived_in` (also small things on surfaces): background detail beyond what you name. Use `lived_in` for working rooms, `bare` when emptiness is the point.
- **actions**: what happens, in order: an action from the catalogue with `who` (a thing's id: every copy does it, each `stagger` of the shot after the last) and its settings; a setting that names the actor takes `who`. Their `start` and `end` are fractions of the scene's length. For now the picture shows where everyone stands as the scene begins: put people where the moment needs them rather than relying on an action to bring them there.
- **lights**: one to three, matching the anchor's `light_and_colour`: a practical lamp, a window, overhead, or outdoor sky; at night, the sources in the scene.
- **camera**: one move, usually the theme move named in the scene's `camera` (the catalogue lists the theme's moves with the move blocks), with its `subject`: a thing's id (all its copies are framed together), or the room's furniture that carries the scene. Its `start`, `elevation` and `framing` set the angle the picture is drawn from.

- **transition** (any scene, staged or drawn, but the last): how it turns into the next scene, when the channel renders its joins: a transition from the catalogue, chosen for the change your `morph_bridge` describes (a calm change flows, a sudden turn rushes through, a descent spirals inward). Leave it empty for the theme's usual join.

Name only what the story needs and what makes the place believable; the furnishing fills the rest.

## Example

A board meeting at night: eight men in suits round the long table, three of them holding a glass of water, files piled at one end, the camera circling them.

```json
{"layout": {"block": "boardroom", "settings": [{"name": "chairs", "value": "4"}]},
 "things": [
   {"thing_id": "men", "what": "man in a suit", "count": 8,
    "height": 1.8, "person": {"pose": "seated", "dress": "suit"},
    "place": {"relation": "seated_at", "target": "table"}},
   {"thing_id": "glasses", "what": "water glass", "count": 3, "height": 0.12,
    "place": {"relation": "held_by", "target": "men"}},
   {"thing_id": "files", "what": "folder", "count": 5, "height": 0.02,
    "place": {"relation": "stacked_on", "target": "table"}}],
 "furnish": "some",
 "actions": [],
 "lights": [{"block": "overhead", "settings": [{"name": "over", "value": "table"}]}],
 "camera": {"block": "orbit", "settings": [{"name": "subject", "value": "men"}]}}
```
