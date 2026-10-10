"""Stitching: every step is deterministic ffmpeg, so the patchwork joins exactly."""

import json
import math
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from content.production import checks, ffmpeg
from content.schemas.media import NarrationClip
from content.theme import (
    BreathSpec,
    CameraFraming,
    CameraMove,
    MorphLayerSpec,
    MusicSpec,
    TextureSpec,
)

# Gentle broadcast compression on the voice: evens out peaks so the mix can reach the
# platforms' loudness without clipping, and keeps speech clear on phone speakers.
VOICE_COMPRESSION = "acompressor=threshold=0.1:ratio=3:attack=5:release=150:makeup=1.5"

# loudnorm's first pass prints its measurements as one JSON object.
LOUDNORM_REPORT = re.compile(r"\{[^{}]*\}")


def narration_track(
    clips: Sequence[tuple[NarrationClip, float]],
    total_seconds: float,
    output: Path,
) -> Path:
    """Place each unit's clip at its start time on one silent-padded 48 kHz track."""
    inputs: list[str | Path] = []
    parts = []
    for index, (clip, start) in enumerate(clips):
        inputs += ["-i", clip.path]
        delay = round(start * 1000)
        parts.append(f"[{index}:a]aresample=48000,adelay={delay}:all=1[a{index}]")
    mix = "".join(f"[a{index}]" for index in range(len(clips)))
    graph = ";".join(
        [*parts, f"{mix}amix=inputs={len(clips)}:normalize=0,apad,atrim=0:{total_seconds:.3f}"]
    )
    ffmpeg.run(*inputs, "-filter_complex", graph, "-ac", "1", "-ar", "48000", output)
    return output


# Silence a voice model leaves before and after speech; the story's own pauses replace it.
TRIM_SILENCE = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.04,"
    "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse"
)


def spoken_clip(source: Path, output: Path, tempo: float) -> Path:
    """Normalise a narration clip to 48 kHz mono wav with the model's leading and trailing
    silence removed, adjusting tempo if needed."""
    filters = f"aresample=48000,{TRIM_SILENCE}" + ("" if tempo == 1 else f",atempo={tempo:.4f}")
    ffmpeg.run("-i", source, "-af", filters, "-ac", "1", output)
    return output


def music_bed(track: Path, seconds: float, output: Path, *, crossfade: float = 3.0) -> Path:
    """The locked track looped with crossfades, trimmed to the video, and faded out."""
    length = ffmpeg.probe(track).duration
    step = max(length - crossfade, crossfade)
    copies = max(math.ceil((seconds - length) / step) + 1, 1)
    inputs: list[str | Path] = []
    for _ in range(copies):
        inputs += ["-i", track]
    chain = "[0:a]aresample=48000[m0]"
    for index in range(1, copies):
        chain += (
            f";[{index}:a]aresample=48000[i{index}]"
            f";[m{index - 1}][i{index}]acrossfade=d={crossfade}[m{index}]"
        )
    fade = min(crossfade, seconds / 4)
    chain += (
        f";[m{copies - 1}]atrim=0:{seconds:.3f},"
        f"afade=t=out:st={seconds - fade:.3f}:d={fade:.3f}[bed]"
    )
    ffmpeg.run(*inputs, "-filter_complex", chain, "-map", "[bed]", output)
    return output


def mix_audio(narration: Path, music: Path | None, spec: MusicSpec, output: Path) -> Path:
    """Set the music a measured distance below the voice, duck it further under speech,
    then normalise the mix for social platforms in two passes so it lands on target."""
    with tempfile.TemporaryDirectory() as directory:
        mixed = Path(directory) / "mix.wav"
        if music is None:
            ffmpeg.run("-i", narration, "-af", VOICE_COMPRESSION, "-ar", "48000", mixed)
        else:
            gain = (
                checks.integrated_loudness(narration)
                - spec.below_voice_db
                - checks.integrated_loudness(music)
            )
            graph = (
                f"[0:a]aresample=48000,{VOICE_COMPRESSION},asplit=2[voice][key];"
                f"[1:a]aresample=48000,volume={gain:.2f}dB[bed];"
                f"[bed][key]sidechaincompress=threshold={spec.duck_threshold}"
                f":ratio={spec.duck_ratio}:attack={spec.duck_attack_ms}"
                f":release={spec.duck_release_ms}[ducked];"
                "[voice][ducked]amix=inputs=2:duration=first:normalize=0"
            )
            ffmpeg.run(
                "-i", narration, "-stream_loop", "-1", "-i", music,
                "-filter_complex", graph, "-ar", "48000", mixed,
            )  # fmt: skip
        target = f"I={spec.loudness_lufs}:TP={spec.true_peak_db}:LRA=11"
        report = ffmpeg.run(
            "-i", mixed, "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"
        )  # fmt: skip
        measured = json.loads(LOUDNORM_REPORT.findall(report)[-1])
        second_pass = (
            f"loudnorm={target}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}"
        )
        ffmpeg.run(
            "-i", mixed, "-af", second_pass, "-ar", "48000", "-c:a", "aac", "-b:a", "320k", output
        )  # fmt: skip
    return output


class Framing(NamedTuple):
    """What the camera shows of a keyframe: how far it is zoomed in, and the point of the
    keyframe at the centre of the view (as fractions of its width and height)."""

    zoom: float
    x: float
    y: float


def conform_segment(
    source: Path,
    output: Path,
    *,
    seconds: float,
    speed: float,
    start: Framing,
    end: Framing,
    layer: MorphLayerSpec,
    width: int,
    height: int,
    fps: int,
) -> Path:
    """Fit one generated morph to its place, and heighten it with the theme's layer. The
    camera carries on from the framing the previous still ends on to the one the next
    begins on, so nothing snaps back to the bare keyframe. As the morph peaks the picture
    warps like liquid, leaves light trails, blooms through a mirrored copy, slides its
    colour plates apart and swings its hues; every effect is zero at both ends, so the
    joins stay seamless. An effect at zero is left out."""
    frames = max(round(seconds * fps), 1)
    half = seconds / 2
    swell = (
        f"format=gbrap,fade=t=in:st=0:d={half:.3f}:alpha=1,"
        f"fade=t=out:st={half:.3f}:d={half:.3f}:alpha=1"
    )
    envelope = f"pow(sin(PI*min(T/{seconds:.3f},1)),2)"
    steps = [
        f"[0:v]setpts=(PTS-STARTPTS)*{speed},fps={fps},"
        f"tpad=stop_mode=clone:stop_duration={seconds:.3f},"
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2},"
        f"{_zoompan(start, end, frames, 1, width, height, fps, ease=True)},format=gbrp[cam]"
    ]
    picture = "cam"
    if layer.warp_pixels:
        warp = (
            f"128+{layer.warp_pixels}*{envelope}*sin(2*PI*(X/W*2+T*0.6))"
            f"*cos(2*PI*(Y/H*1.5-T*0.4))"
            f"+{layer.warp_pixels / 2}*{envelope}*sin(2*PI*(X/W*5-Y/H*4+T*0.9))"
        )
        steps.append(
            _displacement_maps(warp, seconds, width, height, fps)
            + "[cam][xm][ym]displace=edge=mirror[warped]"
        )
        picture = "warped"
    # Washes laid over the picture, each from its own copy: (name, filters from [name]).
    washes = [
        (name, chain)
        for name, chain, strength in (
            (
                "trail",
                f"[trail]lagfun=decay=0.93,{swell},colorchannelmixer=aa={layer.trails}",
                layer.trails,
            ),
            (
                "mirror",
                "[mirror]split[under][over];[over]hflip[flipped];"
                f"[under][flipped]blend=all_mode=lighten,{swell},colorchannelmixer=aa={layer.mirror}",
                layer.mirror,
            ),
            (
                "plates",
                f"[plates]rgbashift=rh=-{layer.plate_shift_pixels}:"
                f"bh={layer.plate_shift_pixels},{swell}",
                layer.plate_shift_pixels,
            ),
        )
        if strength
    ]
    if washes:
        steps.append(
            f"[{picture}]split={len(washes) + 1}[layered0]"
            + "".join(f"[{name}]" for name, _ in washes)
        )
        for index, (name, chain) in enumerate(washes):
            steps.append(f"{chain}[{name}ed]")
            steps.append(f"[layered{index}][{name}ed]overlay=format=auto[layered{index + 1}]")
        picture = f"layered{len(washes)}"
    finish = ["setsar=1", "format=yuv420p"]
    if layer.hue_radians or layer.saturation:
        finish.insert(
            0,
            f"hue=H='{layer.hue_radians}*{envelope.replace('T', 't')}*sin(2*PI*t/{seconds:.3f})':"
            f"s='1+{layer.saturation}*{envelope.replace('T', 't')}'",
        )
    steps.append(f"[{picture}]" + ",".join(finish) + "[out]")
    graph = ";".join(steps)
    ffmpeg.run(
        "-i", source, "-filter_complex", graph, "-map", "[out]", "-frames:v", str(frames),
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16", output,
    )  # fmt: skip
    return output


def hold_ending(video: Path, seconds: float, output: Path) -> Path:
    """Hold the last frame for `seconds` while it fades to black: the picture rests while
    the music plays out."""
    length = ffmpeg.probe(video).duration
    ffmpeg.run(
        "-i", video,
        "-vf", f"tpad=stop_mode=clone:stop_duration={seconds:.3f},"
        f"fade=t=out:st={length:.3f}:d={seconds:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", output,
    )  # fmt: skip
    return output


def finish(
    video: Path,
    audio: Path,
    subtitles: Path,
    fonts_directory: Path,
    output: Path,
    *,
    crf: int = 21,
    preset: str = "slow",
) -> Path:
    """Burn the subtitles and mux the mix into the platform-ready MP4. CRF 21 keeps the
    printed grain without the 250 MB files CRF 18 produced for a minute of video."""
    burn = f"subtitles=filename='{_escape(subtitles)}':fontsdir='{_escape(fonts_directory)}'"
    ffmpeg.run(
        "-i",
        video,
        "-i",
        audio,
        "-vf",
        burn,
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-shortest",
        "-movflags",
        "+faststart",
        output,
    )
    return output


def contact_sheet(images: Sequence[Path], output: Path, *, columns: int = 4) -> Path:
    """A storyboard overview: every keyframe, in order, on one image."""
    rows = math.ceil(len(images) / columns)
    with tempfile.TemporaryDirectory() as directory:
        for index, image in enumerate(images):
            (Path(directory) / f"{index:03d}{image.suffix}").symlink_to(image.resolve())
        ffmpeg.run(
            "-framerate",
            "1",
            "-i",
            Path(directory) / f"%03d{images[0].suffix}",
            "-vf",
            f"scale=270:480,tile={columns}x{rows}:padding=8:color=0x07070A",
            "-frames:v",
            "1",
            output,
        )
    return output


def sample_frames(video: Path, fractions: Sequence[float], directory: Path) -> list[Path]:
    """Still frames at the given fractions of a clip, for a vision model to describe."""
    duration = ffmpeg.probe(video).duration
    directory.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, fraction in enumerate(fractions):
        frame = directory / f"{video.stem}-{index}.png"
        ffmpeg.run("-ss", f"{duration * fraction:.3f}", "-i", video, "-frames:v", "1", frame)
        frames.append(frame)
    return frames


def _escape(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def glide(move: CameraMove, focal: tuple[float, float]) -> tuple[Framing, Framing]:
    """Where the view starts and ends as the theme's camera move glides over a still,
    around its focal point."""
    return _framing(move.start, focal), _framing(move.end, focal)


def landing(point: tuple[float, float], framing: Framing) -> tuple[float, float]:
    """Where a point of the keyframe appears in the frame under `framing`, as fractions;
    the view never leaves the picture, so near an edge the point sits off-centre."""
    view = 1 / framing.zoom
    left = min(max(framing.x - view / 2, 0.0), 1 - view)
    top = min(max(framing.y - view / 2, 0.0), 1 - view)
    return (point[0] - left) * framing.zoom, (point[1] - top) * framing.zoom


def motion_clip(
    image: Path,
    seconds: float,
    start: Framing,
    end: Framing,
    focal: tuple[float, float],
    output: Path,
    *,
    breath: BreathSpec,
    width: int,
    height: int,
    fps: int,
    tint: tuple[str, float] | None = None,
) -> Path:
    """A keyframe brought to life: the camera glides from `start` to `end`, the frame
    breathes, and slow ripples radiate from the focal point (left out at zero). Both fade
    in and out with the clip, so a still meets its morphs exactly on its glide. With a
    `tint` (a colour and an opacity), the ripple crests take on that colour, faintly; the
    picture itself is never recoloured. All ffmpeg, so free."""
    frames = max(round(seconds * fps), 1)
    (sx, sy), (ex, ey) = landing(focal, start), landing(focal, end)
    camera = (
        f"[0:v]scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2},"
        f"{_zoompan(start, end, frames, frames, width, height, fps, ease=False, breath=breath)},"
    )
    graph = _breathing(
        camera, ((sx + ex) / 2, (sy + ey) / 2), seconds, breath, width, height, fps, tint
    )
    ffmpeg.run(
        "-i", image, "-filter_complex", graph, "-map", "[out]", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", output,
    )  # fmt: skip
    return output


def encode_frames(frames: Path, frame_rate: int, output: Path) -> Path:
    """A folder of numbered frames as a video."""
    ffmpeg.run(
        "-framerate", str(frame_rate), "-i", frames / "%04d.png",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", output,
    )  # fmt: skip
    return output


def shot_clip(
    frames: Path,
    frame_rate: int,
    seconds: float,
    focal: tuple[float, float],
    output: Path,
    *,
    breath: BreathSpec,
    width: int,
    height: int,
    fps: int,
    tint: tuple[str, float] | None = None,
) -> Path:
    """A rendered 3D shot (a folder of numbered frames at `frame_rate`) made into a scene's
    clip: fitted to the frame and the cut's rate, cut or held to `seconds`, with the same
    breathing ripples and tint a keyframe gets. The camera move is the shot's own."""
    count = max(round(seconds * fps), 1)
    source = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},tpad=stop_mode=clone:stop_duration={seconds:.3f},"
    )
    graph = _breathing(source, focal, seconds, breath, width, height, fps, tint)
    ffmpeg.run(
        "-framerate", str(frame_rate), "-i", frames / "%04d.png", "-filter_complex", graph,
        "-map", "[out]", "-frames:v", str(count),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", output,
    )  # fmt: skip
    return output


def _breathing(
    source: str,
    centre: tuple[float, float],
    seconds: float,
    breath: BreathSpec,
    width: int,
    height: int,
    fps: int,
    tint: tuple[str, float] | None,
) -> str:
    """The filter graph that ripples a picture from `centre` (left out at zero), its
    crests faintly tinted; `source` is the chain that makes the picture, ending in a comma."""
    rx, ry = centre
    envelope = f"sin(PI*min(T/{seconds:.3f},1))"
    distance = f"hypot(X/W-{rx:.3f},(Y/H-{ry:.3f})*{height / width:.3f})"
    ripple = (
        f"128+{breath.ripple_pixels}*{envelope}*sin(2*PI*({distance}*6-T/{breath.seconds}))"
        f"*(AXIS-CENTRE)/({distance}+0.05)"
    )
    ripples = (
        ripple.replace("AXIS", "X/W").replace("CENTRE", f"{rx:.3f}"),
        ripple.replace("AXIS", "Y/H").replace("CENTRE", f"{ry:.3f}"),
    )
    if not breath.ripple_pixels:
        return source + "setsar=1,format=yuv420p[out]"
    if tint is None or tint[1] <= 0:
        return (
            source
            + "format=yuv420p[cam];"
            + _displacement_maps(ripples, seconds, width, height, fps)
            + "[cam][xm][ym]displace=edge=smear,setsar=1,format=yuv420p[out]"
        )
    colour, opacity = tint
    # How much colour each pixel takes: the ripple's crests, fading in and out with the
    # clip, never more than `opacity`.
    crest = f"255*{opacity:.3f}*{envelope}*abs(sin(2*PI*({distance}*6-T/{breath.seconds})))"
    return (
        source
        + "format=yuv420p[cam];"
        + _displacement_maps(ripples, seconds, width, height, fps)
        + "[cam][xm][ym]displace=edge=smear[rippled];"
        + f"nullsrc=s={max(width // 6, 8)}x{max(height // 6, 8)}:r={fps}:d={seconds:.3f},"
        + f"format=gray,geq=lum='{crest}',scale={width}:{height}:flags=bicubic[crest];"
        + f"color=c=0x{colour.lstrip('#')}:s={width}x{height}:r={fps}:d={seconds:.3f},"
        + "format=yuva420p[colour];[colour][crest]alphamerge[tinted];"
        + "[rippled][tinted]overlay=format=auto,setsar=1,format=yuv420p[out]"
    )


def texture(
    video: Path, output: Path, *, spec: TextureSpec, breath_seconds: float, fps: int
) -> Path:
    """One continuous pass over the whole cut, so nothing pops at a join: a slowly zooming
    Mandelbrot set softly through the shadows, a vignette breathing with the stills, colour
    fringing, printed grain, and a gentle flicker of light. A layer at zero is left out."""
    info = ffmpeg.probe(video)
    if info.width is None or info.height is None:
        raise ValueError(f"{video} has no video stream")
    sources, base = "", "[0:v]"
    if spec.fractal > 0:
        sources = (
            f"mandelbrot=s={info.width // 4}x{info.height // 4}:rate={fps}:start_scale=1.2:"
            "end_scale=0.6:maxiter=60:outer=normalized_iteration_count:inner=black,format=gray,"
            f"scale={info.width}:{info.height}:flags=bicubic,format=yuv420p[fractal];"
        )
        base = f"[0:v][fractal]blend=all_mode=softlight:all_opacity={spec.fractal}:shortest=1,"
    layers = [
        f"vignette=angle='PI/5+{spec.vignette_swing}*sin(2*PI*t/{breath_seconds})':eval=frame"
        if spec.vignette_swing > 0
        else "",
        f"rgbashift=rh=-{spec.fringe_pixels}:bh={spec.fringe_pixels}" if spec.fringe_pixels else "",
        f"noise=alls={spec.grain}:allf=t" if spec.grain else "",
        f"eq=brightness='{spec.flicker}*sin(2*PI*t*0.7)':eval=frame" if spec.flicker > 0 else "",
    ]
    chain = ",".join([*(layer for layer in layers if layer), "setsar=1", "format=yuv420p"])
    graph = sources + base + chain + "[out]" if base != "[0:v]" else f"[0:v]{chain}[out]"
    ffmpeg.run(
        "-i", video, "-filter_complex", graph, "-map", "[out]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", output,
    )  # fmt: skip
    return output


def _framing(spec: CameraFraming, focal: tuple[float, float]) -> Framing:
    fx, fy = focal
    return Framing(
        spec.zoom,
        fx + (0.5 - fx) * spec.toward_centre + spec.x,
        fy + (0.5 - fy) * spec.toward_centre + spec.y,
    )


def _zoompan(
    start: Framing,
    end: Framing,
    frames: int,
    duration: int,
    width: int,
    height: int,
    fps: int,
    *,
    ease: bool,
    breath: BreathSpec | None = None,
) -> str:
    """zoompan from one framing to another over `frames` output frames; `duration` is
    frames per input frame (all of them for a still, one for a video)."""
    progress = f"min(on/{max(frames - 1, 1)},1)"
    if ease:
        progress = f"({progress}*{progress}*(3-2*{progress}))"
    zoom = f"({start.zoom}+({end.zoom}-{start.zoom})*{progress})"
    if breath is not None:
        zoom += f"*(1+{breath.swell}*sin(2*PI*on/{fps}/{breath.seconds})*sin(PI*{progress}))"
    centre_x = f"({start.x}+({end.x}-{start.x})*{progress})"
    centre_y = f"({start.y}+({end.y}-{start.y})*{progress})"
    return (
        f"zoompan=z='{zoom}':x='max(0,min(iw-iw/zoom,{centre_x}*iw-iw/zoom/2))':"
        f"y='max(0,min(ih-ih/zoom,{centre_y}*ih-ih/zoom/2))':"
        f"d={duration}:s={width}x{height}:fps={fps}"
    )


def _displacement_maps(
    fields: str | tuple[str, str], seconds: float, width: int, height: int, fps: int
) -> str:
    """Two displacement maps ([xm], [ym]) from per-pixel expressions of X, Y and T, drawn
    at a sixth of the frame and smoothly enlarged: full-size per-pixel maths was many
    times slower, and the fields are smooth anyway."""
    horizontal, vertical = (
        fields
        if isinstance(fields, tuple)
        else (
            fields,
            fields.replace("X/W", "Q").replace("Y/H", "X/W").replace("Q", "Y/H"),
        )
    )
    maps = []
    for field, label in ((horizontal, "xm"), (vertical, "ym")):
        maps.append(
            f"nullsrc=s={max(width // 6, 8)}x{max(height // 6, 8)}:r={fps}:d={seconds:.3f},"
            f"format=gray,geq=lum='{field}',"
            f"scale={width}:{height}:flags=bicubic[{label}];"
        )
    return "".join(maps)


def dissolve_join(
    clips: Sequence[tuple[Path, float]], output: Path, *, joins: Sequence[float], fps: int
) -> Path:
    """Join clips without moving any scene's start. `joins[i]` is how long clip i melts
    into the next: a still into a still dissolves over a hold of its last frame, while a
    still and its morph meet frame to frame (0), since the morph carries on its glide."""
    inputs: list[str | Path] = []
    parts = []
    for index, (clip, seconds) in enumerate(clips):
        inputs += ["-i", clip]
        hold = joins[index] if index < len(clips) - 1 else 0.0
        parts.append(
            f"[{index}:v]fps={fps},setpts=PTS-STARTPTS,trim=duration={seconds:.3f},"
            f"tpad=stop_mode=clone:stop_duration={seconds + hold:.3f},"
            f"trim=duration={seconds + hold:.3f},setpts=PTS-STARTPTS,settb=1/{fps},"
            f"format=yuv420p[v{index}]"
        )
    joined, offset = "[v0]", 0.0
    for index in range(1, len(clips)):
        offset += clips[index - 1][1]
        label = f"[x{index}]"
        dissolve = joins[index - 1]
        parts.append(
            f"{joined}[v{index}]xfade=transition=fade:duration={dissolve:.3f}:"
            f"offset={offset:.3f}{label}"
            if dissolve > 0
            # A joined stream comes out on concat's own clock; put it back on the frame
            # clock, or a dissolve after it cannot match its inputs.
            else f"{joined}[v{index}]concat=n=2:v=1:a=0,settb=1/{fps}{label}"
        )
        joined = label
    parts.append(f"{joined}null[out]")
    ffmpeg.run(
        *inputs, "-filter_complex", ";".join(parts), "-map", "[out]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", output,
    )  # fmt: skip
    return output
