.PHONY: test lint selftest campaign report
test:
	python -m pytest
lint:
	ruff check .
selftest:
	inferencepilot selftest
campaign report:
	@echo "$@ is not implemented in M0"; exit 2
