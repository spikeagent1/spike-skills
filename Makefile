.PHONY: validate test

validate: test
	python3 tools/validate_repo.py

test:
	python3 -m py_compile tools/validate_repo.py tests/test_validate_repo.py
	python3 -m unittest discover -s tests
