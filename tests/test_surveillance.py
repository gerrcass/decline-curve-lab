"""Behaviour of the lift-candidate screening rules.

A **lift candidate** is a well flagged by a simple screening rule — low oil rate, high
water cut, or a sustained wellhead-pressure decline — as warranting engineering review.
The flag is for a human to act on or dismiss; it is never a recommendation, so no test
here reads a flag as a decision.

Every screening rule is evaluated on a well's **most recent production period**, which
is what an engineer looking at the dashboard this morning has in front of them. The
boundary cases matter more than the middle of the distribution here: a threshold that
includes its own equality is a threshold that eventually flags a well at exactly the
rate the rule was written to let through.
"""

from __future__ import annotations

import pandas as pd
import pytest

from decline_curve_lab import io, metrics, surveillance

#: The columns the screen reads, in the order the screening frame reports them.
EXPECTED_SCREENING_COLUMNS = (
    "well_id",
    "latest_date",
    "qo",
    "water_cut",
    "wellhead_pressure",
    "candidate_lift",
    "lift_reasons",
)


def production_csv(well_id: str, production_periods) -> str:
    """Format one well's production periods as the CSV text these tests read back.

    Each production period is ``(date, qo, qw, qg, wellhead_pressure)``. Building the
    input by hand in the test bodies would bury the numbers a boundary test is about in
    CSV quoting, so the fixtures below stay readable as rates and pressures.
    """
    header = "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
    rows = "".join(
        f"{date},{well_id},{qo},{qw},{qg},{wellhead_pressure},0.25\n"
        for date, qo, qw, qg, wellhead_pressure in production_periods
    )
    return header + rows


def production_rows_csv(wells) -> str:
    """Format several wells' production periods into one CSV, header written once."""
    header = "date,well_id,qo,qw,qg,wellhead_pressure,choke\n"
    return header + "".join(
        production_csv(well_id, periods).split("\n", 1)[1] for well_id, periods in wells
    )


def reorder_periods(text: str) -> str:
    """Keep a production CSV's header and list its production periods back to front.

    A production CSV may list a well's production periods in any order, so this is a
    legitimate way for one to arrive. Which production period a well is screened on is
    its latest date, not whichever period the file happened to write last.
    """
    header, *rows = text.splitlines(keepends=True)
    return "".join([header, *reversed(rows)])


def read_measured(tmp_path, text: str, name: str = "production.csv") -> pd.DataFrame:
    """Read a production CSV and derive its metrics, the frame the screen is given."""
    csv_path = tmp_path / name
    csv_path.write_text(text, encoding="utf-8")
    return metrics.compute_metrics(io.load_production(csv_path))


def screen(tmp_path, text: str, name: str = "production.csv") -> pd.DataFrame:
    """Read a production CSV and screen it for lift candidates, end to end."""
    return surveillance.flag_lift_candidates(
        read_measured(tmp_path, text, name)
    )


def screened_well(tmp_path, text: str, name: str = "production.csv") -> dict:
    """The one well of a single-well CSV, as a plain dict for readable assertions."""
    screened = screen(tmp_path, text, name)
    assert list(screened["well_id"]) == [
        screened["well_id"].iloc[0]
    ], "these fixtures hold exactly one well"
    return screened.iloc[0].to_dict()


# A well whose oil rate falls below 100 bbl/d *and* whose water cut rises above 0.7 by
# its most recent production period. Both halves of the rate rule are reachable from
# the fixture, so a screen that only checked one of them would still pass the mid-range
# case and be caught by the boundary tests below.
#
# qo 150 -> 150, water cut 150/(150+50) = 0.25, wellhead pressure steady.
# qo  99 ->  99, water cut  99/( 99+ 1) = 0.01, wellhead pressure steady.
# qo  30 ->  30, water cut  30/( 30+70) = 0.70  <- exactly at the threshold, not above.
# qo  30 ->  30, water cut  30/( 30+90) = 0.75  <- above both thresholds.
LOW_RATE_HIGH_WATER_CUT = [
    ("2024-01-01", 150.0, 50.0, 3000.0, 250.0),
    ("2024-02-01", 99.0, 1.0, 2000.0, 250.0),
    ("2024-03-01", 30.0, 70.0, 600.0, 250.0),
    ("2024-04-01", 30.0, 90.0, 600.0, 250.0),
]

# A well whose wellhead pressure falls every production period, so the three most
# recent production periods give three consecutive declines and the screen flags it.
# Its oil rate and water cut stay clear of both rate thresholds, so the pressure rule
# is the only thing that can flag this well.
STEADILY_FALLING_PRESSURE = [
    ("2024-01-01", 500.0, 50.0, 5000.0, 260.0),
    ("2024-02-01", 490.0, 45.0, 4900.0, 240.0),
    ("2024-03-01", 480.0, 40.0, 4800.0, 220.0),
    ("2024-04-01", 470.0, 35.0, 4700.0, 200.0),
]

# The same well's pressure shape with one decline held flat at the end: 260 -> 240 ->
# 220 -> 220 is two declines, not three. Equal pressures are not a decline, so this
# must not flag.
TWO_DECLINES_THEN_FLAT = [
    ("2024-01-01", 500.0, 50.0, 5000.0, 260.0),
    ("2024-02-01", 490.0, 45.0, 4900.0, 240.0),
    ("2024-03-01", 480.0, 40.0, 4800.0, 220.0),
    ("2024-04-01", 470.0, 35.0, 4700.0, 220.0),
]

# A well the rate rule flags on its own: low oil rate (50 bbl/d) with high water cut
# (250/300 = 0.833), on a wellhead pressure that does not fall three periods running, so
# the pressure rule has nothing to say about it.
HIGH_RATE_AND_WATER_CUT = [
    ("2024-01-01", 60.0, 200.0, 1200.0, 100.0),
    ("2024-02-01", 55.0, 220.0, 1100.0, 100.0),
    ("2024-03-01", 50.0, 250.0, 1000.0, 100.0),
    ("2024-04-01", 50.0, 250.0, 1000.0, 100.0),
]

# A well both rules reach: the same low oil rate and high water cut, on a wellhead
# pressure that falls every production period (160 -> 130 -> 100 -> 80, three consecutive
# declines). The two rules are independent, so a well can trip both.
BOTH_RULES = [
    ("2024-01-01", 60.0, 200.0, 1200.0, 160.0),
    ("2024-02-01", 55.0, 220.0, 1100.0, 130.0),
    ("2024-03-01", 50.0, 250.0, 1000.0, 100.0),
    ("2024-04-01", 50.0, 250.0, 1000.0, 80.0),
]


def test_a_well_is_screened_once_with_the_inputs_the_rules_were_read_from(tmp_path):
    """One row per well, carrying the production period the rules were evaluated on.

    The screen's job is to tell an engineer which well and which production period the
    flag is about, so both travel with the flag rather than being re-derived downstream.
    """
    screened = screen(tmp_path, production_csv("W-1", LOW_RATE_HIGH_WATER_CUT))

    assert tuple(screened.columns) == EXPECTED_SCREENING_COLUMNS
    assert screened["well_id"].tolist() == ["W-1"]
    # The most recent production period is the last row, and its numbers are the ones
    # both rules are read from.
    assert screened["latest_date"].iloc[0] == pd.Timestamp("2024-04-01")
    assert screened["qo"].iloc[0] == 30.0
    assert screened["water_cut"].iloc[0] == pytest.approx(0.75)
    assert screened["wellhead_pressure"].iloc[0] == 250.0


def test_oil_rate_below_the_threshold_with_high_water_cut_flags_a_lift_candidate(tmp_path):
    screened = screened_well(tmp_path, production_csv("W-1", LOW_RATE_HIGH_WATER_CUT))

    assert screened["candidate_lift"] is True
    assert screened["lift_reasons"] == (surveillance.LOW_RATE_HIGH_WATER_CUT,)


@pytest.mark.parametrize(
    ("qo", "qw", "water_cut", "flags"),
    [
        # 100 bbl/d is the ~100 bbl/d artificial-lift heuristic on a *daily average* oil
        # rate (ADR-0002), so the equality itself is inside the flag and only a rate
        # strictly below it flags. `qo` is the oil rate alone; `qw` sets the water cut.
        (99.999, 900.0, 900.0 / 999.999, True),
        (99.999, 0.0, 0.0, False),
        # Exactly 100 bbl/d is *not* below the threshold, whatever the water cut is.
        (100.0, 900.0, 0.9, False),
        (100.0, 300.0, 0.75, False),
        (100.0, 100.0, 0.5, False),
        (100.0, 70.0, 70.0 / 170.0, False),
        (100.0001, 100.0, 100.0 / 200.0001, False),
        (100.0001, 900.0, 900.0 / 1000.0001, False),
        (30.0, 70.0, 0.7, False),
        # The tightest water-cut neighbours of 0.7 reachable on a two-decimal grid with
        # the oil rate below the rate threshold, so the water cut alone decides the flag:
        # 228.67/(98+228.67) = 0.70000306 and 226.33/(97+226.33) = 0.69999691. These are
        # the values either side of the threshold, so a rule that treated the threshold
        # as approximate rather than exact would give the wrong answer for one of them.
        (98.0, 228.67, 0.7000030611932532, True),
        (97.0, 226.33, 0.69999690718461, False),
        (29.0, 70.0, 70.0 / 99.0, True),
        (30.0, 900.0, 900.0 / 930.0, True),
        (30.0, 0.0, 0.0, False),
        (0.0, 200.0, 1.0, True),
    ],
)
def test_the_rate_rule_is_evaluated_on_exact_boundaries(
    tmp_path, qo, qw, water_cut, flags
):
    """`qo == 100` and `water cut == 0.7` are inside the rule, not outside it.

    Both thresholds are strict comparisons, so a value sitting exactly on a threshold
    does not flag while its neighbours either side do. That is the whole content of the
    default: at 100 bbl/d with a water cut of 0.7 the well is producing enough liquid,
    with enough oil in it, that a human reviewer should not be handed it as a screen.
    """
    # The first production period only sets up the well; the flag is read off the most
    # recent one, which is what the rates below describe.
    production_periods = [
        ("2024-01-01", 500.0, 50.0, 5000.0, 250.0),
        ("2024-02-01", qo, qw, 1000.0, 250.0),
    ]
    screened = screened_well(tmp_path, production_csv("W-1", production_periods))

    assert screened["water_cut"] == pytest.approx(water_cut)
    assert screened["candidate_lift"] is flags
    if flags:
        assert surveillance.LOW_RATE_HIGH_WATER_CUT in screened["lift_reasons"]
    else:
        assert screened["lift_reasons"] == ()


def test_the_water_cut_threshold_is_exactly_seven_tenths(tmp_path):
    """The high-water-cut threshold is a named 0.7, read from the rule's own default."""
    assert surveillance.DEFAULT_HIGH_WATER_CUT == 0.7


def test_the_lift_rate_threshold_is_a_daily_average_of_one_hundred_barrels_per_day(tmp_path):
    """The ~100 bbl/d heuristic compares against a daily average, per ADR-0002.

    The rate column is a daily average over the production period, so the threshold is
    a daily average too. A monthly volume read into this comparison would flag every
    well in the fleet and is the mistake this assertion guards.
    """
    assert surveillance.DEFAULT_LIFT_RATE_BBL_D == 100.0


def test_low_oil_rate_alone_does_not_flag_without_high_water_cut(tmp_path):
    """Both halves of the rate rule have to hold; a low rate on its own is not a flag.

    Water is what makes a low rate a lift question: a well at 30 bbl/d of oil and 0.1 of
    water cut is a healthy oil well that happens to be small.
    """
    production_periods = [
        ("2024-01-01", 500.0, 50.0, 5000.0, 250.0),
        ("2024-02-01", 30.0, 1.0, 600.0, 250.0),
    ]
    screened = screened_well(tmp_path, production_csv("W-1", production_periods))

    assert screened["qo"] == 30.0
    assert screened["water_cut"] < surveillance.DEFAULT_HIGH_WATER_CUT
    assert screened["candidate_lift"] is False
    assert screened["lift_reasons"] == ()


def test_high_water_cut_alone_does_not_flag_above_the_rate_threshold(tmp_path):
    """The rate rule is an *and*, so plenty of water with plenty of oil is not a flag."""
    production_periods = [
        ("2024-01-01", 500.0, 50.0, 5000.0, 250.0),
        ("2024-02-01", 400.0, 400.0, 4000.0, 250.0),
    ]
    screened = screened_well(tmp_path, production_csv("W-1", production_periods))

    assert screened["qo"] > surveillance.DEFAULT_LIFT_RATE_BBL_D
    assert screened["water_cut"] == 0.5
    assert screened["candidate_lift"] is False
    assert screened["lift_reasons"] == ()


def test_three_consecutive_wellhead_pressure_declines_flag_a_lift_candidate(tmp_path):
    """Falling wellhead pressure across three consecutive production periods flags.

    The pressure rule is three consecutive period-over-period declines ending at the
    well's most recent production period: 260 -> 240 -> 220 -> 200 is three declines,
    and needs four production periods to see them.
    """
    screened = screened_well(tmp_path, production_csv("W-1", STEADILY_FALLING_PRESSURE))

    assert surveillance.DEFAULT_PRESSURE_DECLINE_COUNT == 3
    assert screened["candidate_lift"] is True
    assert screened["lift_reasons"] == (surveillance.SUSTAINED_PRESSURE_DECLINE,)


def test_two_consecutive_wellhead_pressure_declines_do_not_flag_a_lift_candidate(tmp_path):
    """Two declines are not the rule the screen applies; three are.

    A single step down in wellhead pressure is a well being operated, and a screen that
    flagged on two would fill the review list with wells whose pressure recovered.
    """
    screened = screened_well(tmp_path, production_csv("W-1", TWO_DECLINES_THEN_FLAT))

    assert screened["candidate_lift"] is False
    assert screened["lift_reasons"] == ()


def test_equal_wellhead_pressures_are_not_a_decline(tmp_path):
    """A flat wellhead pressure is not falling, however many production periods show it.

    Nothing is declining, so no amount of a constant pressure can add up to the three
    declines the rule asks for.
    """
    production_periods = [
        (f"2024-0{month}-01", 500.0, 50.0, 5000.0, 250.0) for month in range(1, 7)
    ]
    screened = screened_well(tmp_path, production_csv("W-1", production_periods))

    assert screened["candidate_lift"] is False
    assert screened["lift_reasons"] == ()


def test_three_production_periods_cannot_show_three_declines(tmp_path):
    """Three production periods hold two periods of change, so they cannot flag.

    The rule needs four observations to see three declines. A well too young to hold
    that history is unflagged, not flagged by a shortened read of the rule: there is no
    evidence of a sustained decline yet.
    """
    production_periods = STEADILY_FALLING_PRESSURE[:3]
    screened = screened_well(tmp_path, production_csv("W-1", production_periods))

    assert screened["candidate_lift"] is False
    assert screened["lift_reasons"] == ()


def test_four_production_periods_of_falling_pressure_are_enough_to_flag(tmp_path):
    """Four production periods are the shortest history that can satisfy the rule."""
    production_periods = STEADILY_FALLING_PRESSURE[:4]
    screened = screened_well(tmp_path, production_csv("W-1", production_periods))

    assert screened["candidate_lift"] is True
    assert screened["lift_reasons"] == (surveillance.SUSTAINED_PRESSURE_DECLINE,)


def test_a_decline_that_recovered_before_the_most_recent_production_period_is_not_a_flag(
    tmp_path,
):
    """The three declines have to *end* at the most recent production period.

    A well that fell and then came back up is not in a sustained decline now, and the
    screen describes the well as it stands rather than as it once was.
    """
    production_periods = [
        ("2024-01-01", 500.0, 50.0, 5000.0, 260.0),
        ("2024-02-01", 490.0, 45.0, 4900.0, 240.0),
        ("2024-03-01", 480.0, 40.0, 4800.0, 220.0),
        ("2024-04-01", 470.0, 35.0, 4700.0, 200.0),
        ("2024-05-01", 460.0, 30.0, 4600.0, 250.0),
    ]
    screened = screened_well(tmp_path, production_csv("W-1", production_periods))

    assert screened["candidate_lift"] is False
    assert screened["lift_reasons"] == ()


def test_the_screen_reads_the_most_recent_production_period_by_date(tmp_path):
    """Which production period a well is screened on is its latest date, not its last row.

    A production CSV may list a well's production periods in any order, so screening
    whichever row happens to come last would report a flag against a production period
    the well left behind months ago.
    """
    screened = screened_well(
        tmp_path, reorder_periods(production_csv("W-1", LOW_RATE_HIGH_WATER_CUT))
    )

    assert screened["latest_date"] == pd.Timestamp("2024-04-01")
    assert screened["candidate_lift"] is True


def test_a_falling_wellhead_pressure_flags_a_well_with_no_high_water_cut(tmp_path):
    """The pressure rule stands on its own; it does not need the rate rule to agree."""
    screened = screened_well(tmp_path, production_csv("W-1", STEADILY_FALLING_PRESSURE))

    assert screened["qo"] > surveillance.DEFAULT_LIFT_RATE_BBL_D
    assert screened["water_cut"] < surveillance.DEFAULT_HIGH_WATER_CUT
    assert screened["lift_reasons"] == (surveillance.SUSTAINED_PRESSURE_DECLINE,)


def test_both_rules_firing_records_both_reasons_not_just_the_first(tmp_path):
    """Every reason that fired is recorded, so a reviewer sees the whole case.

    One reason is a summary; two reasons are two separate things to look at, and the
    panel showing the well is the place that says which.
    """
    screened = screened_well(tmp_path, production_csv("W-1", BOTH_RULES))

    assert screened["candidate_lift"] is True
    assert set(screened["lift_reasons"]) == {
        surveillance.LOW_RATE_HIGH_WATER_CUT,
        surveillance.SUSTAINED_PRESSURE_DECLINE,
    }


def test_every_reason_has_a_label_a_human_can_read(tmp_path):
    """The wording shown beside a flag lives with the rule, not in the dashboard."""
    for reason in surveillance.LIFT_REASON_LABELS:
        assert surveillance.LIFT_REASON_LABELS[reason].strip()


def test_a_well_no_rule_reaches_is_left_unflagged_with_no_reason(tmp_path):
    """A well clear of every threshold is in the frame, unflagged, with nothing claimed.

    The screen reports on the whole fleet, so a reviewer can see which wells were
    looked at and passed, rather than only the ones that tripped something.
    """
    production_periods = [
        ("2024-01-01", 500.0, 50.0, 5000.0, 250.0),
        ("2024-02-01", 450.0, 40.0, 4500.0, 255.0),
    ]
    screened = screened_well(tmp_path, production_csv("W-1", production_periods))

    assert screened["candidate_lift"] is False
    assert screened["lift_reasons"] == ()


def test_each_well_is_screened_on_its_own_production_periods(tmp_path):
    """One well's oil rate or pressure says nothing about another well's flag.

    The rules are read per well, so screening the fleet flags the wells that trip and
    leaves the rest of the fleet alone, one row per well and sorted by well id.
    """
    wells = [
        # Flags on the rate rule: 50 bbl/d of oil with a water cut of 250/300 = 0.833,
        # on a flat wellhead pressure.
        ("W-FLAGS-RATE", HIGH_RATE_AND_WATER_CUT),
        # Flags on the pressure rule: three consecutive declines, 260 -> 240 -> 220 -> 200.
        ("W-FLAGS-PRESSURE", STEADILY_FALLING_PRESSURE),
        # Flags on neither: low water cut, pressure rising.
        ("W-CLEAR", LOW_RATE_HIGH_WATER_CUT[:3]),
    ]
    screened = screen(tmp_path, production_rows_csv(wells))

    assert screened["well_id"].tolist() == ["W-CLEAR", "W-FLAGS-PRESSURE", "W-FLAGS-RATE"]
    assert dict(zip(screened["well_id"], screened["candidate_lift"])) == {
        "W-CLEAR": False,
        "W-FLAGS-PRESSURE": True,
        "W-FLAGS-RATE": True,
    }
    reasons = dict(zip(screened["well_id"], screened["lift_reasons"]))
    assert reasons["W-CLEAR"] == ()
    assert reasons["W-FLAGS-PRESSURE"] == (surveillance.SUSTAINED_PRESSURE_DECLINE,)
    assert reasons["W-FLAGS-RATE"] == (surveillance.LOW_RATE_HIGH_WATER_CUT,)


def test_the_pressure_decline_count_is_a_parameter_the_screen_honours(tmp_path):
    """The decline count is the screen's own parameter, not a number baked into it.

    A field that reads sustained decline as four periods rather than three gets four,
    and the three-decline well above stops being a flag without the rule being edited.
    """
    measured = read_measured(tmp_path, production_csv("W-1", STEADILY_FALLING_PRESSURE))

    stricter = surveillance.flag_lift_candidates(measured, pressure_declines=4)

    # Three declines is not four, so the same well is no longer a lift candidate.
    assert stricter["candidate_lift"].tolist() == [False]
    assert stricter["lift_reasons"].tolist() == [()]


def test_a_decline_count_that_needs_no_decline_is_rejected(tmp_path):
    """A rule requiring no decline would flag every well, so it is refused outright.

    ``pressure_declines = 0`` is the degenerate case a caller could reach by
    arithmetic on the default. Screening a constant wellhead pressure under it would
    hand a reviewer the whole fleet, so the screen says no instead.
    """
    measured = read_measured(tmp_path, production_csv("W-1", STEADILY_FALLING_PRESSURE))

    with pytest.raises(ValueError, match="pressure_declines"):
        surveillance.flag_lift_candidates(measured, pressure_declines=0)


def test_screening_does_not_mutate_the_metrics_it_is_given(tmp_path):
    """The metrics frame is the caller's; screening reads it and leaves it alone."""
    measured = read_measured(tmp_path, production_csv("W-1", HIGH_RATE_AND_WATER_CUT))
    before = measured.copy()

    surveillance.flag_lift_candidates(measured)

    pd.testing.assert_frame_equal(measured, before)


def test_screening_needs_the_derived_metrics_and_says_which_column_is_missing(tmp_path):
    """The screen reads `water_cut`, so it belongs to the frame the metrics produce.

    Reporting the missing column by name means a caller that passed a bare production
    frame can see what to derive, rather than being told the screen did not work.
    """
    csv_path = tmp_path / "production.csv"
    csv_path.write_text(
        production_csv("W-1", STEADILY_FALLING_PRESSURE), encoding="utf-8"
    )
    production = io.load_production(csv_path)

    with pytest.raises(io.SchemaError, match="water_cut"):
        surveillance.flag_lift_candidates(production)


def test_the_committed_sample_data_flags_the_two_wells_it_should(tmp_path):
    """The rule has to bite on the sample fleet, which is what the dashboard ships.

    Read from the committed sample production CSV through the same path the dashboard
    takes, so this is the fleet a reviewer sees rather than a hand-built stand-in.
    """
    measured = metrics.compute_metrics(io.load_production(io.SAMPLE_CSV_PATH))

    screened = surveillance.flag_lift_candidates(measured)
    flags = dict(zip(screened["well_id"], screened["lift_reasons"]))

    # DCL-04 is the waterlogged well: at 50.6 bbl/d of oil with a water cut of 0.85 on
    # its most recent production period it trips the rate rule on its own, and its
    # wellhead pressure is rising, so there is only one reason to give.
    assert flags["DCL-04"] == (surveillance.LOW_RATE_HIGH_WATER_CUT,)
    # DCL-03 is the well losing pressure: 79.9 -> 77.2 -> 74.6 -> 72.1 psi over its four
    # most recent production periods is three consecutive declines, while it is still
    # well above 100 bbl/d of oil and well below a water cut of 0.7.
    assert flags["DCL-03"] == (surveillance.SUSTAINED_PRESSURE_DECLINE,)
    # The rest of the fleet trips neither rule. DCL-02 and DCL-06 are below 100 bbl/d but
    # above a water cut of 0.7, so they are the wells that would flag if the rate rule
    # were an *or* rather than an *and*.
    for well_id in ("DCL-01", "DCL-02", "DCL-05", "DCL-06"):
        assert flags[well_id] == (), f"{well_id} was not expected to flag"