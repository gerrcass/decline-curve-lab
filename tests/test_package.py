"""The package's public API surface: what it exports, and what it holds back."""

from __future__ import annotations

import inspect

import decline_curve_lab
from decline_curve_lab import arps


def test_the_decline_curve_selection_is_exported():
    """``DeclineCurveSelection`` is what ``select_decline_curve`` returns.

    It is the headline type of the library — a caller holding a selection needs to name it
    to annotate the variable, and ``from decline_curve_lab import *`` has to hand it over —
    so it belongs in ``__all__`` alongside the function that returns it. It did not, and
    nothing caught that: the ordering assert in ``__init__.py`` only checks the order of
    the names that *are* there, which says nothing about the ones that are not.
    """
    assert decline_curve_lab.DeclineCurveSelection is arps.DeclineCurveSelection
    assert "DeclineCurveSelection" in decline_curve_lab.__all__


def test_every_public_name_the_package_defines_is_exported():
    """A public name bound in the package but missing from ``__all__`` is a bug.

    ``__all__`` is the API: it is what ``from decline_curve_lab import *`` gives a caller
    and what a documentation tool reads. A name bound in the package namespace but missing
    from it is reachable as an attribute and invisible to both, which is how
    ``DeclineCurveSelection`` stayed unexported for a release. Submodules are the one
    public name that is not in ``__all__`` and that is on purpose — they are reached as
    ``decline_curve_lab.arps``, not imported by name — so they are excluded here too.
    """
    public = {
        name
        for name, value in vars(decline_curve_lab).items()
        if not name.startswith("_") and not inspect.ismodule(value)
    }

    assert public == set(decline_curve_lab.__all__)


def test_the_public_api_holds_no_effective_decline_value():
    """No exported object reports an effective decline, per ADR-0001 and the glossary.

    ``D_eff = ln(1 + Di)`` is *derived only to solve the continuous exponential* and is
    never stored or reported. A public property on an exported type puts it on the API as
    a reported value however carefully it is labelled — which is what
    ``TerminalSwitch.tail_effective_decline`` did, with exactly one internal caller. The
    derivation itself stays public on ``arps.effective_decline_from_nominal``, because that
    is a function that computes a value rather than a field that reports one.
    """
    exported = [
        getattr(decline_curve_lab, name)
        for name in decline_curve_lab.__all__
        if inspect.isclass(getattr(decline_curve_lab, name))
    ]
    reported = {
        f"{value.__name__}.{name}"
        for value in exported
        for name in dir(value)
        if not name.startswith("_") and "effective_decline" in name
    }

    assert reported == set(), (
        "an exported type reports an effective decline, which ADR-0001 rules out: "
        f"{sorted(reported)}"
    )


def test_the_terminal_switch_reports_the_nominal_terminal_decline_only():
    """The switch's own decline parameter is the nominal one, and it is a field.

    The tail is solved with an effective decline derived from this field, so the field is
    what a caller reads and the derivation stays inside the solver.
    """
    switch = decline_curve_lab.terminal_switch(
        decline_curve_lab.HyperbolicFit(
            qi=800.0, Di=0.6, b=0.5, r_squared=0.99, rmse_bbl_d=1.0, n_production_periods=36,
            n_dropped=0,
        )
    )

    assert switch is not None
    assert switch.terminal_decline_annual == decline_curve_lab.DEFAULT_TERMINAL_DECLINE_ANNUAL
    assert not hasattr(switch, "tail_effective_decline")
