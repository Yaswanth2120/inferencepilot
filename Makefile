.PHONY: test lint selftest campaign report
OUT ?= reports/generated
test:
	python -m pytest
lint:
	ruff check .
selftest:
	inferencepilot selftest
campaign:
	@test -n "$(PLAN)" -a -n "$(DB)" || { echo 'Set PLAN and DB'; exit 2; }
	bash scripts/run_campaign.sh "$(PLAN)" "$(DB)" $(EXECUTE)
report:
	@test -n "$(DB)" -a -n "$(EXPERIMENT)" || { echo 'Set DB and EXPERIMENT'; exit 2; }
	inferencepilot report --db "$(DB)" --experiment "$(EXPERIMENT)" --out "$(OUT)"
