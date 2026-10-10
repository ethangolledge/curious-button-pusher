# Story regression examples

`content eval --config <your config>` replays the scripts here through the listener test, the
comprehension questions and the free checks, and reports whether they catch the failures a
person named. Each example is a folder:

- `negative.json`: a script a person rejected, each failure they named pinned to its line
  (`expected`: the kind of failure, the line, and a note in their words).
- `positive.json` (optional): the version they approved. Any flag on it is a false alarm.

`the-great-stink/` is a made-up sample showing the format. Replace it with your own channel's
rejected scripts once you have some: they make the checks answer to your taste. Running them is
paid (a listener call and a few dozen judge calls per example), so it is not part of the tests.
