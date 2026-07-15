from app.segments import group_turns


def test_group_turns_merges_consecutive_same_speaker():
    segs = [
        {"start": 0.0, "end": 1.0, "speaker": "A", "text": "one"},
        {"start": 1.0, "end": 2.0, "speaker": "A", "text": "two"},
        {"start": 2.0, "end": 3.0, "speaker": "B", "text": "three"},
        {"start": 3.0, "end": 4.0, "speaker": "A", "text": "four"},
    ]
    turns = group_turns(segs)
    assert [len(t) for t in turns] == [2, 1, 1]
    assert [t[0]["speaker"] for t in turns] == ["A", "B", "A"]


def test_group_turns_empty():
    assert group_turns([]) == []
