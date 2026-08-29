"""The runtime installer, in three parts: render, io, cli.

`tools/install_skill.py` is the entry point and re-exports every public name, so
`tools/check_staging.py` and the tests import one module and never need to know
which part a helper lives in.
"""
