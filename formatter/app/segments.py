from __future__ import annotations

from typing import Dict, List


def group_turns(segments: List[Dict]) -> List[List[Dict]]:
    """Group a flat segment list into contiguous same-speaker turns."""
    turns: List[List[Dict]] = []
    for seg in segments:
        if turns and turns[-1][-1]["speaker"] == seg["speaker"]:
            turns[-1].append(seg)
        else:
            turns.append([seg])
    return turns
