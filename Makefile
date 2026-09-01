.PHONY: start validate test index eval-baseline eval-doctor eval-report eval-routing eval-skill stage-openclaw

EVAL_MODEL ?= sonnet
EVAL_GRADER ?= opus
ROUTING_MODE ?= native

# The whole gate, and the only thing CI runs: .github/workflows/validate.yml
# calls this target on both legs (with and without jsonschema) so a check added
# here is a check CI runs, not one it silently skips.
validate: test
	python3 tools/validate_repo.py
	python3 tools/check_citations.py
	python3 tools/build_index.py --check

# The one command a newcomer runs: it probes this host, asks for the local
# values the adapter leaves as placeholders, installs `home` and the starter
# set through tools/install_skill.py, and verifies with one real invocation.
# Not the default goal -- `make` on its own still runs the gate.
start:
	python3 tools/bootstrap.py

# Globbed, not listed: a module the list forgot was a module CI never compiled.
test:
	python3 -m py_compile tools/*.py tools/*/*.py tests/*.py
	python3 -m unittest discover -s tests

# Stages every OpenClaw-eligible skill into dist/, then verifies the staged
# tree: zero runtime-specific hits, every backticked vocabulary term resolved,
# and metadata.openclaw.requires.* consistent with each Dependencies line. The
# installer's own exit code is not fatal here -- it is 1 whenever it refuses a
# skill (an UNCONFIRMED adapter term), which is the tool reporting correctly,
# not a staging failure; check_staging.py is what decides this target's exit.
stage-openclaw:
	-python3 tools/install_skill.py --runtime openclaw --all --dest dist/openclaw/workspace/skills
	python3 tools/check_staging.py --runtime openclaw --dest dist/openclaw/workspace

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
