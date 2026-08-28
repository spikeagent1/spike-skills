.PHONY: validate test eval-doctor eval-report eval-skill

EVAL_MODEL ?= sonnet
EVAL_GRADER ?= opus

validate: test
	python3 tools/validate_repo.py

test:
	python3 -m py_compile tools/validate_repo.py tools/run_evals.py tools/evalrunner/*.py tests/test_validate_repo.py tests/test_run_evals.py
	python3 -m unittest discover -s tests

eval-doctor:
	python3 tools/run_evals.py doctor --model $(EVAL_MODEL)

eval-report:
	python3 tools/run_evals.py report --run $(RUN)

eval-skill:
	python3 tools/run_evals.py run --skill $(SKILL) --model $(EVAL_MODEL) --grader-model $(EVAL_GRADER) --compare-baseline
