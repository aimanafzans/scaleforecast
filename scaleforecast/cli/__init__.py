"""
ScaleForecast CLI presentation + controller layer.

Package layout:

    app.py            -- header + interpreter-status Panel + main loop + dispatch
    console.py        -- the single shared rich Console + theme
    components.py     -- reusable renderers (table / menu / paginator / error panel)
    session.py        -- SessionState shared across controllers
    controllers/
        base.py       -- shared selectors + back-nav helper
        generate.py   -- Option 1
        manage.py     -- Option 2
        forecast.py    -- Option 3
        reports.py     -- Option 4  (the big UX fix -- two-step discoverable flow)
        benchmark.py   -- Option 5

The legacy :mod:`scaleforecast.main` is kept as a thin shim that just
delegates to :func:`scaleforecast.cli.app.run`.
"""

from scaleforecast.cli.app import run

__all__ = ["run"]