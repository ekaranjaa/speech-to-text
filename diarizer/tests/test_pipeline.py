from app.pipeline import run_diarization


class FakeTranscriber:
    def __init__(self, words, language="en"):
        self._words = words
        self._language = language

    def transcribe(self, audio_path):
        return self._words, self._language


class FakeDiarizer:
    def __init__(self, turns):
        self._turns = turns
        self.received_num_speakers = "unset"

    def diarize(self, audio_path, num_speakers):
        self.received_num_speakers = num_speakers
        return self._turns


def test_run_diarization_shape():
    words = [
        {"start": 0.0, "end": 1.0, "word": " Hello"},
        {"start": 6.0, "end": 7.0, "word": " Hi"},
    ]
    turns = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
        {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
    ]
    diar = FakeDiarizer(turns)
    result = run_diarization("x.wav", FakeTranscriber(words), diar, num_speakers=2)
    assert result["language"] == "en"
    assert result["speakers"] == ["SPEAKER_00", "SPEAKER_01"]
    assert result["segments"][0] == {
        "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Hello",
    }
    assert diar.received_num_speakers == 2


def test_run_diarization_no_turns_defaults_single_speaker():
    words = [{"start": 0.0, "end": 1.0, "word": " Solo"}]
    result = run_diarization("x.wav", FakeTranscriber(words), FakeDiarizer([]))
    assert result["speakers"] == ["SPEAKER_00"]
