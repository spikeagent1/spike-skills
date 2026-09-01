"""The repository validator, one module per family of rules.

`tools/validate_repo.py` is the entry point: it composes these modules, walks the
skills, and prints the report. Every public name here is re-exported there, so a
caller (the eval runner, the installer, the staging check) imports from
`tools.validate_repo` and never needs to know which module a rule lives in.
"""
