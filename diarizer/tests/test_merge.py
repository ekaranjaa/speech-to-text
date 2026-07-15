from app.merge import assign_speaker, build_segments

TURNS = [
    {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
    {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
]


def test_assign_speaker_by_containment():
    assert assign_speaker({"start": 1.0, "end": 2.0, "word": " hi"}, TURNS) == "SPEAKER_00"
    assert assign_speaker({"start": 6.0, "end": 7.0, "word": " yo"}, TURNS) == "SPEAKER_01"


def test_assign_speaker_nearest_when_outside():
    # midpoint 11.5 is past every turn -> nearest is SPEAKER_01
    assert assign_speaker({"start": 11.0, "end": 12.0, "word": " end"}, TURNS) == "SPEAKER_01"


def test_assign_speaker_no_turns_uses_default():
    assert assign_speaker({"start": 1.0, "end": 2.0, "word": " hi"}, []) == "SPEAKER_00"


def test_build_segments_groups_by_speaker():
    words = [
        {"start": 0.0, "end": 1.0, "word": " Hello"},
        {"start": 1.0, "end": 2.0, "word": " there"},
        {"start": 6.0, "end": 7.0, "word": " Hi"},
        {"start": 7.0, "end": 8.0, "word": " back"},
    ]
    assert build_segments(words, TURNS) == [
        {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "Hello there"},
        {"start": 6.0, "end": 8.0, "speaker": "SPEAKER_01", "text": "Hi back"},
    ]


def test_build_segments_empty():
    assert build_segments([], TURNS) == []
