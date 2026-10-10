from content.schemas.script import ScriptUnit
from content.story.prose import (
    dense_issues,
    fragment_issues,
    question_issues,
    repetition_issues,
    setup_question_issues,
    stock_phrase_issues,
)

# Lines shaped like those a person heard as having "no soul", and their fixes.


def test_a_long_verbless_line_is_flagged_and_a_sentence_is_not() -> None:
    robotic = _script("The minister's brother, speaking in Geneva.")
    told = _script("He said it as the minister's brother, speaking in Geneva.")

    (issue,) = fragment_issues(robotic)

    assert issue.startswith("U1:") and "has no verb" in issue
    assert fragment_issues(told) == []


def test_a_sentence_whose_verb_is_a_contraction_is_not_a_fragment() -> None:
    # The tagger reads "doesn't" as one unknown word; spelled out, it is a verb.
    told = _script("Even so, something here doesn't sit right.", "They won't say why.")

    assert fragment_issues(told) == []


def test_one_or_two_short_fragments_land_but_more_sound_like_a_list() -> None:
    two = _script("Both at once.", "He stayed on as chief executive.", "Hard to say.")
    three = _script("Both at once.", "By August, no reply.", "Hard to say.")

    assert fragment_issues(two) == []
    (issue,) = fragment_issues(three)
    assert issue.startswith("3 short verbless lines")


def test_a_sentence_with_too_many_new_names_and_figures_is_flagged() -> None:
    overloaded = _script(
        "Auditors at the Treasury found that, through 2019, Northgate had billed the "
        "Ministry of Works about forty-two million pounds, including twelve million in "
        "March 2018 alone."
    )
    told = _script(
        "Auditors at the Treasury looked at what Northgate had billed the Ministry of Works.",
        "By 2019 it came to about forty-two million pounds, for work nobody had checked.",
    )

    (issue,) = dense_issues(overloaded)

    assert issue.startswith("U1:") and "brings in 7 new names and figures" in issue
    assert dense_issues(told) == []


def test_names_already_heard_and_small_counts_are_not_new_load() -> None:
    script = _script(
        "Northgate won the Ministry of Works contract from the Treasury.",
        "Two years later, Northgate, the Ministry of Works and the Treasury met in March "
        "2018 to sign six more deals.",
    )

    assert dense_issues(script) == []


def test_a_short_question_answered_at_once_is_a_setup() -> None:
    setup = _script("And the money? Six months after leaving office, his firm won the contract.")
    open_ending = _script("His firm won the contract.", "So what could that harbour become?")

    (issue,) = setup_question_issues(setup)

    assert '"And the money?"' in issue
    assert setup_question_issues(open_ending) == []


def test_an_ending_that_restates_the_story_is_flagged() -> None:
    story = _script(
        "He promised a fleet of up to a hundred and eighty ships.",
        "Though one filing already lists a hundred and eighty ships.",
    )
    fresh = _script(
        "He promised a fleet of up to a hundred and eighty ships.",
        "Worth millions. But to whom?",
    )

    (issue,) = repetition_issues(story, ["U2"])

    assert "hundred and eighty" in issue
    assert repetition_issues(fresh, ["U2"]) == []


def test_a_figure_repeated_in_the_ending_is_flagged() -> None:
    story = _script("The fund put in money in 2022.", "By 2022 the money was already in.")

    (issue,) = repetition_issues(story, ["U2"])

    assert "(2022)" in issue


def test_shared_number_words_and_names_are_not_restatements() -> None:
    # Both were false alarms on a real run and spent paid rewrites.
    story = _script(
        "Lawmakers asked the Bank of England one question about his two jobs.",
        "And the Bank of England has not said where one role ends and the other begins.",
    )

    assert repetition_issues(story, ["U2"]) == []


def _script(*texts: str) -> list[ScriptUnit]:
    return [
        ScriptUnit(
            unit_id=f"U{index}",
            order=index,
            narrative_function="hook" if index == 1 else "context",
            arc_phase_id="P1",
            transition_intent="build",
            text=text,
            claim_ids=["C1"],
        )
        for index, text in enumerate(texts, start=1)
    ]


def test_a_short_form_of_a_name_already_heard_is_not_new() -> None:
    script = _script(
        "Northgate Holdings won the Ministry of Works contract.",
        "By 2019, Northgate had billed the Ministry about forty-two million pounds, through "
        "the Treasury, in March 2018.",
    )

    assert dense_issues(script) == []


def test_more_than_two_questions_before_the_ending_sound_like_a_presenter() -> None:
    two = _script("Who paid for it?", "The fund did.", "Why so much?", "No one said.")
    three = _script("Who paid?", "The fund.", "Why?", "No one said.", "And who knew?", "End?")

    assert question_issues(two, ending=["U4"]) == []
    (issue,) = question_issues(three, ending=["U6"])
    assert issue.startswith("3 questions before the ending")
    # The ending's own question never counts.
    assert question_issues(three, ending=["U5", "U6"]) == []


def test_stock_phrases_are_pointed_out() -> None:
    script = _script("Even so, something doesn't add up.", "Here's the thing: it was legal.")

    issues = stock_phrase_issues(script)

    assert [issue.split(":")[0] for issue in issues] == ["U1", "U2"]
    assert stock_phrase_issues(_script("The sums added up to two billion.")) == []
