PYTHON ?= python3
PIPX ?= pipx
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_STAMP := $(VENV)/.installed
WHEEL_DIR := dist

.PHONY: install build test typecheck coverage clean

# Install the eblook-mcp command into an isolated pipx environment.
install:
	$(PIPX) install --force .

# Create the virtualenv and install the project with dev dependencies.
$(VENV_STAMP): pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install -e '.[dev]'
	touch $(VENV_STAMP)

# Build a wheel into dist/ using the project virtualenv.
build: $(VENV_STAMP)
	$(VENV_PYTHON) -m pip wheel --no-deps --wheel-dir $(WHEEL_DIR) .

# Run strict type checking on the library package and the tests.
typecheck: $(VENV_STAMP)
	$(VENV_PYTHON) -m mypy --strict eblook_mcp tests

# Run the test suite in the project virtualenv.
test: typecheck
	$(VENV_PYTHON) -m pytest

# Run the tests and report line coverage of the library package.
coverage: $(VENV_STAMP)
	$(VENV_PYTHON) -m pytest --cov=eblook_mcp --cov-report=term-missing

clean:
	rm -rf $(VENV) $(WHEEL_DIR) build *.egg-info .pytest_cache .coverage htmlcov
