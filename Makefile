.PHONY: validate test index eval-baseline eval-doctor eval-report eval-routing eval-skill

EVAL_MODEL ?= sonnet
EVAL_GRADER ?= opus
ROUTING_MODE ?= native

validate: test
	python3 tools/validate_repo.py

test:
	python3 -m py_compile tools/validate_repo.py tools/run_evals.py tools/contracts_check.py tools/build_index.py tools/evalrunner/*.py tests/test_validate_repo.py tests/test_run_evals.py tests/test_contracts.py tests/test_build_index.py
	python3 -m unittest discover -s tests

index:
	python3 tools/build_index.py

eval-baseline:
	python3 tools/run_evals.py run --all --model $(EVAL_MODEL) --grader-model $(EVAL_GRADER) --label baseline
	python3 tools/run_evals.py routing --all --model $(EVAL_MODEL) --mode native --repeats 3 --label baseline

eval-doctor:
	python3 tools/run_evals.py doctor --model $(EVAL_MODEL)

eval-report:
	python3 tools/run_evals.py report --run $(RUN)

eval-routing:
	python3 tools/run_evals.py routing --all --model $(EVAL_MODEL) --mode $(ROUTING_MODE)

eval-skill:
	python3 tools/run_evals.py run --skill $(SKILL) --model $(EVAL_MODEL) --grader-model $(EVAL_GRADER) --compare-baseline --fail-on-ungraded
