import pytest

from backend.mission_summary import summarize_window


def test_summary_percentages_and_contiguous_windows():
    samples = [
        {"time": f"2026-10-03T{hour:02d}:{minute:02d}:00Z", "sun": {"visible": sun}, "earth": {"visible": earth}}
        for hour, minute, sun, earth in (
            (0, 0, True, True),
            (0, 30, False, True),
            (1, 0, False, False),
            (1, 30, True, False),
            (2, 0, True, True),
        )
    ]
    result = summarize_window("test-site", samples, "2026-10-03T00:00:00Z", "2026-10-03T02:00:00Z", 30)

    assert result["sunlight_percent"] == 50
    assert result["earth_visible_percent"] == 50
    assert result["both_available_percent"] == 25
    assert result["longest_darkness_minutes"] == 60
    assert result["longest_comm_blackout_minutes"] == 60
    assert result["windows"]["sunlight"] == [
        {"start": "2026-10-03T00:00:00Z", "end": "2026-10-03T00:30:00Z"},
        {"start": "2026-10-03T01:30:00Z", "end": "2026-10-03T02:00:00Z"},
    ]
    assert result["windows"]["both"] == [
        {"start": "2026-10-03T00:00:00Z", "end": "2026-10-03T00:30:00Z"},
    ]


def test_summary_uses_partial_last_interval_without_substep_claim():
    samples = [
        {"time": "2026-10-03T00:00:00Z", "sun": {"visible": False}, "earth": {"visible": True}},
        {"time": "2026-10-03T00:30:00Z", "sun": {"visible": True}, "earth": {"visible": True}},
        {"time": "2026-10-03T01:00:00Z", "sun": {"visible": True}, "earth": {"visible": True}},
    ]
    result = summarize_window("test-site", samples, "2026-10-03T00:00:00Z", "2026-10-03T01:10:00Z", 30)
    assert result["sunlight_percent"] == pytest.approx(57.1, abs=0.1)
    assert result["windows"]["sunlight"] == [
        {"start": "2026-10-03T00:30:00Z", "end": "2026-10-03T01:10:00Z"},
    ]
