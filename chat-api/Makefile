PY?=python
VENVDIR=.venv

.PHONY: venv install dev-install run-http test

venv:
	$(PY) -m venv $(VENVDIR)

install: venv
	. $(VENVDIR)/bin/activate && pip install -U pip && pip install -r requirements.txt

dev-install: install
	. $(VENVDIR)/bin/activate && pip install -r requirements-dev.txt

run-http:
	. $(VENVDIR)/bin/activate && $(PY) - <<'PY'
import json
from lambda-functions.chat_http_handler import lambda_handler
with open('events/sample_http_event.json') as f:
    event = json.load(f)
print(lambda_handler(event, {}))
PY

test:
	. $(VENVDIR)/bin/activate && pytest -q tests/test_chat_http_handler.py
