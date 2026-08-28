.PHONY: validate test eval-doctor

EVAL_MODEL ?= sonnet

validate: test
	python3 tools/validate_repo.py

test:
	python3 -m py_compile tools/validate_repo.py tools/run_evals.py tools/evalrunner/*.py tests/test_validate_repo.py tests/test_run_evals.py
	python3 -m unittest discover -s tests

eval-doctor:
	python3 tools/run_evals.py doctor --model $(EVAL_MODEL)
