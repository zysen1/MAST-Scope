.PHONY: install test eval demo ui

install:
	pip install -e ".[dev,openai,langgraph,microsoft,otel,eval]"

test:
	PYTHONPATH=src python -m pytest

eval:
	PYTHONPATH=src python -m mast_scope.cli eval
	PYTHONPATH=src python -m inspect_ai src/mast_scope/eval/inspect_task.py --model mockllm/model --display plain

demo:
	PYTHONPATH=src python -m mast_scope.cli demo
	PYTHONPATH=src python -m mast_scope.cli export-demo ui/public/cases

ui:
	cd ui && npm install && npm run build
