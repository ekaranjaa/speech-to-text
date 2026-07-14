from app.seed_profiles import (
    CLEAN_VERBATIM_INSTRUCTIONS,
    FULL_VERBATIM_INSTRUCTIONS,
    SEED_PROFILES,
)


def test_both_prompts_have_italics_rule():
    for text in (CLEAN_VERBATIM_INSTRUCTIONS, FULL_VERBATIM_INSTRUCTIONS):
        low = text.lower()
        assert "italic" in low
        assert "film" in low and "book" in low


def test_both_prompts_forbid_quoting_unintelligible():
    for text in (CLEAN_VERBATIM_INSTRUCTIONS, FULL_VERBATIM_INSTRUCTIONS):
        assert "unintelligible" in text.lower()


def test_seed_profiles_intact():
    assert [p["id"] for p in SEED_PROFILES] == ["full-verbatim", "clean-verbatim"]
