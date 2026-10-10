"""Exact checks for the writing that makes narration sound robotic, found on scripts a
person heard as having "no soul":

- **Verbless fragments.** "The minister's brother, speaking in Geneva." has no finite verb,
  so the voice reads it as a standalone dramatic statement between long pauses. A short
  fragment can land ("Both at once."); a long one, or many short ones, cannot.
- **Pre-fixed questions.** "And the money? Six months after…": a short question the
  very next sentence answers is a set-up, not curiosity.
- **Overloaded sentences.** One sentence that brings in five or more new names and figures
  (a body, a date, a sum, another body, another sum) is more than one hearing holds; the
  listener stops following. A name or figure heard earlier is not new load.
- **Too many questions.** A storyteller asks one or two questions the facts raise; a
  narration full of them sounds like a presenter building suspense. The ending's own
  question does not count.
- **Stock phrases** ("something does not add up", "the plot thickens"): advice only, since a
  phrase list cannot tell an earned use from a lazy one.
- **An ending that repeats.** The ending should send the listener back to the hook with a
  question, not restate a figure or phrase already heard. On replay, a bare number word
  ("one question" … "one role ends") and a name were false alarms that spent paid
  rewrites, so number words count only inside a repeated phrase and names never count.

Finite verbs come from NLTK's averaged-perceptron part-of-speech tagger (downloaded once,
about 3 MB, into NLTK's own data folder).
"""

import re
from collections.abc import Callable, Sequence

from content.schemas.script import ScriptUnit

# A verbless sentence this long reads as a dramatic statement.
LONG_FRAGMENT_WORDS = 5
# Short fragments that may land in one script.
MAX_SHORT_FRAGMENTS = 2
# A question this short, answered by the next sentence, is a set-up.
SETUP_QUESTION_WORDS = 6
# New names and figures one sentence may bring in; more, and a listener stops following.
MAX_NEW_DETAILS = 4
# Questions before the ending passage: more sound like a presenter building suspense.
MAX_QUESTIONS = 2
# Phrases that sound generated or borrowed, matched with contractions expanded.
STOCK_PHRASES = (
    "does not add up",
    "does not sit right",
    "raises questions",
    "raises serious questions",
    "the plot thickens",
    "here is the thing",
    "make no mistake",
    "little did",
    "sent shockwaves",
    "only time will tell",
    "it remains to be seen",
    "at the end of the day",
    "but that is not all",
    "the rest is history",
    "where things get interesting",
)
NUMBER_WORDS = frozenset(
    {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}
    | {"eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen"}
    | {"eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy"}
    | {"eighty", "ninety", "hundred", "thousand", "million", "billion", "trillion"}
)
# Small counts ("two boards", "six months") are easy to hold and are not counted.
SMALL_COUNTS = frozenset({"one", "two", "three", "four", "five", "six", "seven", "eight"})
MONTHS = frozenset(
    {"january", "february", "march", "april", "may", "june", "july", "august"}
    | {"september", "october", "november", "december"}
)
# Lower-case words that join the parts of one name: "Bank of England", "Charles de Gaulle".
NAME_JOINS = frozenset({"of", "bin", "de", "al", "von", "van"})
FINITE_TAGS = frozenset({"VBD", "VBP", "VBZ", "MD"})
STOPWORDS = frozenset(
    {"a", "an", "the", "of", "to", "in", "on", "at", "for", "and", "or", "but", "so"}
    | {"as", "by", "with", "from", "that", "this", "it", "is", "was", "be", "its", "his"}
    | {"her", "their", "he", "she", "they", "we", "you", "i", "what", "who", "how"}
)


def sentences(units: Sequence[ScriptUnit]) -> list[tuple[str, str]]:
    """(unit ID, sentence) for every sentence, in order."""
    return [
        (unit.unit_id, sentence)
        for unit in units
        for sentence in re.split(r"(?<=[.!?])\s+", unit.text.strip())
        if sentence.strip()
    ]


def fragment_issues(units: Sequence[ScriptUnit]) -> list[str]:
    fragments = [
        (unit_id, sentence)
        for unit_id, sentence in sentences(units)
        if not sentence.endswith("?") and not _has_finite_verb(sentence)
    ]
    issues = [
        f'{unit_id}: "{sentence}" has no verb, so it is read as a dramatic statement with long '
        "pauses; fold it into the sentence it belongs to, or give it a verb."
        for unit_id, sentence in fragments
        if len(_words(sentence)) >= LONG_FRAGMENT_WORDS
    ]
    short = [(unit_id, s) for unit_id, s in fragments if len(_words(s)) < LONG_FRAGMENT_WORDS]
    if len(short) > MAX_SHORT_FRAGMENTS:
        issues.append(
            f"{len(short)} short verbless lines ("
            + ", ".join(f'{unit_id} "{s}"' for unit_id, s in short)
            + f"); one or two land, more sound like a list: keep at most {MAX_SHORT_FRAGMENTS}."
        )
    return issues


def dense_issues(units: Sequence[ScriptUnit]) -> list[str]:
    """Sentences that bring in more new names and figures than one hearing holds."""
    heard: set[str] = set()
    issues = []
    for unit_id, sentence in sentences(units):
        details = _details(sentence)
        new = list(dict.fromkeys(detail for detail in details if not _heard(detail, heard)))
        heard.update(detail.lower() for detail in details)
        if len(new) > MAX_NEW_DETAILS:
            issues.append(
                f'{unit_id}: "{sentence}" brings in {len(new)} new names and figures '
                f"({', '.join(new)}); a listener holds one or two at a time. Keep what this "
                "beat needs, say what each means, and move or cut the rest."
            )
    return issues


def _heard(detail: str, heard: set[str]) -> bool:
    """Heard already, in full or in part: "Affinity" after "Affinity Partners"."""
    lower = detail.lower()
    return any(
        lower == name or name.startswith(f"{lower} ") or lower.startswith(f"{name} ")
        for name in heard
    )


def setup_question_issues(units: Sequence[ScriptUnit]) -> list[str]:
    spoken = sentences(units)
    return [
        f'{unit_id}: "{sentence}" is answered by the very next sentence, so it reads as a '
        "set-up. Let the facts raise the question, or hold it open for a beat."
        for (unit_id, sentence), (_, following) in zip(spoken, spoken[1:], strict=False)
        if sentence.endswith("?")
        and len(_words(sentence)) <= SETUP_QUESTION_WORDS
        and not following.endswith("?")
    ]


def question_issues(units: Sequence[ScriptUnit], ending: Sequence[str]) -> list[str]:
    """More questions before the ending than a storyteller would ask."""
    asked = [
        (unit_id, sentence)
        for unit_id, sentence in sentences(units)
        if sentence.endswith("?") and unit_id not in ending
    ]
    if len(asked) <= MAX_QUESTIONS:
        return []
    listed = ", ".join(f'{unit_id} "{sentence}"' for unit_id, sentence in asked)
    return [
        f"{len(asked)} questions before the ending ({listed}); a storyteller asks one or two "
        f"that the facts raise: keep at most {MAX_QUESTIONS} and tell the rest."
    ]


def stock_phrase_issues(units: Sequence[ScriptUnit]) -> list[str]:
    """Phrases that sound generated or borrowed; advice, never a forced rewrite."""
    return [
        f'{unit.unit_id}: "{phrase}" is a stock phrase; say what actually happened instead.'
        for unit in units
        for phrase in STOCK_PHRASES
        if phrase in _expanded(unit.text).lower().replace("’", "'").replace("here's", "here is")
    ]


def repetition_issues(units: Sequence[ScriptUnit], ending: Sequence[str]) -> list[str]:
    """Figures or three-word phrases in the ending units that the story already said."""
    before = [unit for unit in units if unit.unit_id not in ending]
    closing = [unit for unit in units if unit.unit_id in ending]
    said = {phrase for unit in before for phrase in _phrases(unit.text)}
    names = {name for unit in units for name in _names(unit.text)}
    repeated = sorted({p for unit in closing for p in _phrases(unit.text)} & said - names)
    if not repeated:
        return []
    return [
        f"The ending repeats what the story already said ({'; '.join(repeated)}): return to "
        "the hook with the story's central question, sharpened by what it showed, without "
        "restating it."
    ]


def _phrases(text: str) -> set[str]:
    words = _words(text.lower())
    figures = {word for word in words if word.isdigit()}
    return figures | _trigrams(words)


def _names(text: str) -> set[str]:
    """Three-word phrases whose every content word is capitalised: "the Bank of England"."""
    words = _words(text)
    return {
        " ".join(words[i : i + 3]).lower()
        for i in range(len(words) - 2)
        if all(word[0].isupper() for word in words[i : i + 3] if word.lower() not in STOPWORDS)
    } & _trigrams([word.lower() for word in words])


def _details(sentence: str) -> list[str]:
    """The names (runs of proper nouns) and figures (runs of numbers, with a month joined to
    its year) in one sentence, in order. Possessives are dropped, so "London's" is "London"."""
    words = re.findall(r"[A-Za-z]+(?:[-'’][A-Za-z]+)*|\d[\d,.]*\d|\d", sentence)
    words = [re.sub(r"['’]s$", "", word) for word in words]
    tags = [tag for _, tag in _tagger()(words)] if words else []
    details: list[str] = []
    run: list[str] = []
    kind = ""

    def close() -> None:
        nonlocal run, kind
        text = " ".join(run)
        if run and not (kind == "figure" and text.lower() in SMALL_COUNTS):
            details.append(text)
        run, kind = [], ""

    for index, (word, tag) in enumerate(zip(words, tags, strict=True)):
        lower = word.lower()
        is_number = word[0].isdigit() or all(part in NUMBER_WORDS for part in lower.split("-"))
        if is_number or lower in MONTHS:
            word_kind = "figure"
        elif tag in ("NNP", "NNPS"):
            word_kind = "name"
        else:
            word_kind = ""
        joins_name = (
            kind == "name"
            and lower in NAME_JOINS
            and index + 1 < len(tags)
            and tags[index + 1] in ("NNP", "NNPS")
        )
        joins_figure = (
            kind == "figure"
            and lower == "and"
            and index + 1 < len(words)
            and (words[index + 1].lower().split("-")[0] in NUMBER_WORDS)
        )
        if joins_name or joins_figure or (word_kind and word_kind == kind):
            run.append(word)
        else:
            close()
            if word_kind:
                run, kind = [word], word_kind
    close()
    return details


def _trigrams(words: list[str]) -> set[str]:
    return {
        " ".join(words[i : i + 3])
        for i in range(len(words) - 2)
        if sum(word not in STOPWORDS for word in words[i : i + 3]) >= 2
    }


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+(?:-[A-Za-z']+)*|\d+", text)


def _has_finite_verb(sentence: str) -> bool:
    return any(tag in FINITE_TAGS for _, tag in _tagger()(_words(_expanded(sentence))))


# Contractions spelled out before tagging: the tagger reads "doesn't" as one unknown word
# (an adjective), which made "Something here doesn't sit right." look verbless.
CONTRACTIONS = (
    (r"\bwon['’]t\b", "will not"),
    (r"\bcan['’]t\b", "can not"),
    (r"n['’]t\b", " not"),
    (r"['’]re\b", " are"),
    (r"['’]ve\b", " have"),
    (r"['’]ll\b", " will"),
    (r"['’]m\b", " am"),
)


def _expanded(sentence: str) -> str:
    for pattern, replacement in CONTRACTIONS:
        sentence = re.sub(pattern, replacement, sentence, flags=re.IGNORECASE)
    return sentence


def _tagger() -> Callable[[list[str]], list[tuple[str, str]]]:
    import nltk

    try:
        nltk.data.find("taggers/averaged_perceptron_tagger_eng")
    except LookupError:
        nltk.download("averaged_perceptron_tagger_eng", quiet=True)
    tag: Callable[[list[str]], list[tuple[str, str]]] = nltk.pos_tag
    return tag
