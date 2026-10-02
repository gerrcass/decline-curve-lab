"""The package's entry point: regenerate the committed sample production CSV.

``python -m decline_curve_lab`` runs this, and this is the command ``make sample-data``
and the README document.

It exists so that the documented command **calls** :func:`decline_curve_lab.synthetic.main`
rather than re-executing the generator module. ``decline_curve_lab/__init__.py`` imports
the generator, so ``python -m decline_curve_lab.synthetic`` asks ``runpy`` to execute a
module that is already in ``sys.modules``; ``runpy`` warns about exactly that ("found in
sys.modules ... may result in unpredictable behaviour"), and any environment that promotes
warnings to errors — ``-W error::RuntimeWarning``, ``PYTHONWARNINGS``, a test runner — turns
the documented command into a hard failure. Importing the generator normally and calling
``main()`` once runs the same code with no warning.

``decline_curve_lab.synthetic`` still keeps its own ``if __name__ == "__main__"`` block, so
``python -m decline_curve_lab.synthetic`` remains supported; it is simply the spelling that
warns.

Args:
    argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

Returns:
    ``0``.
"""

from __future__ import annotations

from decline_curve_lab.synthetic import main

if __name__ == "__main__":
    raise SystemExit(main())
