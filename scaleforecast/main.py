"""
ScaleForecast CLI entry point.  Delegates to :mod:`scaleforecast.cli.app.run`.
"""

import sys


def main():
    """Compatibility entry point that delegates to the new CLI package."""
    from scaleforecast.cli.app import run

    if sys.platform == "win32":
        import multiprocessing
        multiprocessing.freeze_support()
    run()


if __name__ == "__main__":
    main()