from app.exports import format_timestamp, to_markdown, to_srt, to_txt, to_vtt

SEGS = [
    {"start": 0.0, "end": 2.5, "speaker": "Interviewer", "text": "I loved *Friends*."},
    {"start": 2.5, "end": 4.0, "speaker": "Guest", "text": "Me too."},
]


def test_format_timestamp_srt_and_vtt():
    assert format_timestamp(3661.5) == "01:01:01,500"
    assert format_timestamp(3661.5, comma=False) == "01:01:01.500"


def test_to_srt():
    out = to_srt(SEGS)
    assert "1\n00:00:00,000 --> 00:00:02,500\nInterviewer: I loved <i>Friends</i>." in out
    assert "2\n00:00:02,500 --> 00:00:04,000\nGuest: Me too." in out


def test_to_vtt():
    out = to_vtt(SEGS)
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500\n<v Interviewer>I loved <i>Friends</i>.</v>" in out


def test_to_txt_strips_markdown():
    out = to_txt(SEGS)
    assert "Interviewer: I loved Friends." in out
    assert "Guest: Me too." in out
    assert "*" not in out and "<i>" not in out


def test_to_markdown_keeps_emphasis_and_bold_labels():
    out = to_markdown(SEGS)
    assert "**Interviewer:** I loved *Friends*." in out
    assert "**Guest:** Me too." in out
