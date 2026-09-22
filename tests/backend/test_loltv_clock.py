import pytest
from metiquo_worker.loltv_clock import frame_duration


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        (None, None),
        ([], None),
        ([{"type": "GOLD", "clock": True}], None),
        ([{"type": "GOLD", "clock": 100000}], 0),
        ([{"type": "GOLD", "clock": 180900}, {"type": "GOLD", "clock": 100000}], 80),
        (
            [
                {"type": "GOLD", "clock": 100000},
                {"type": "PAUSE", "value": "start", "clock": 120000, "clock_end": 131000},
                {"type": "PAUSE", "value": "end", "clock": 130000},
                {"type": "GOLD", "clock": 180000},
            ],
            69,
        ),
        (
            [
                {"type": "GOLD", "clock": 100000},
                {"type": "PAUSE", "value": "start", "clock": 120000},
                {"type": "PAUSE", "value": "end", "clock": 130000},
                {"type": "PAUSE", "value": "start", "clock": 150000, "clock_end": 170000},
                {"type": "GOLD", "clock": 180000},
            ],
            50,
        ),
        (
            [
                {"type": "GOLD", "clock": 100000},
                {"type": "PAUSE", "value": "start", "clock": 150000},
                {"type": "GOLD", "clock": 180000},
            ],
            50,
        ),
        (
            [
                {"type": "GOLD", "clock": 100000},
                {"type": "PAUSE", "value": "end", "clock": 130000},
                {"type": "GOLD", "clock": 180000},
            ],
            None,
        ),
        (
            [
                {"type": "PAUSE", "value": "start", "clock": 80000, "clock_end": 95000},
                {"type": "GOLD", "clock": 100000},
                {"type": "GOLD", "clock": 180000},
            ],
            80,
        ),
    ],
)
def test_duration_uses_only_the_published_clock_and_pause_intervals(events, expected):
    assert frame_duration(events) == expected


def test_captured_pyramid_frame_excludes_94_second_pause():
    # Actual source frame 59de34363894e471c173fb9f, 2026-09-21T19:14:39.960Z.
    assert (
        frame_duration(
            [
                {"type": "ITEM", "clock": 1790015930000},
                {
                    "type": "PAUSE",
                    "value": "start",
                    "clock": 1790017055000,
                    "clock_end": 1790017149000,
                },
                {"type": "PAUSE", "value": "end", "clock": 1790017148000},
                {"type": "GOLD", "clock": 1790018079000},
            ]
        )
        == 2055
    )


def test_captured_pyramid_first_game_matches_cumulative_source_pause_correction():
    # LoLTV shows 36:28, subtracting all three published corrections (70 s),
    # even though the first two entries overlap. Interval union gives 36:39.
    assert (
        frame_duration(
            [
                {"type": "ITEM", "clock": 1790012411000},
                {
                    "type": "PAUSE",
                    "value": "start",
                    "clock": 1790012454000,
                    "clock_end": 1790012499000,
                },
                {
                    "type": "PAUSE",
                    "value": "start",
                    "clock": 1790012488000,
                    "clock_end": 1790012499000,
                },
                {"type": "PAUSE", "value": "end", "clock": 1790012498000},
                {
                    "type": "PAUSE",
                    "value": "start",
                    "clock": 1790014325000,
                    "clock_end": 1790014339000,
                },
                {"type": "PAUSE", "value": "end", "clock": 1790014338000},
                {"type": "GOLD", "clock": 1790014669000},
            ]
        )
        == 2188
    )
