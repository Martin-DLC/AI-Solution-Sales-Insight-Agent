# Codex Workspace Rules

- Only modify files inside the current Git repository root and its subdirectories.
- Run `git rev-parse --show-toplevel` before each task.
- If the current directory is not the project root, stop immediately.
- The Codex client `which python` output is not required to point directly to `.venv`.
- All Python commands must use `./.venv/bin/python`.
- All pip commands must use `./.venv/bin/python -m pip`.
- All pytest commands must use `./.venv/bin/python -m pytest`.
- Do not use system `python`, `pip3`, or global pip to install project dependencies.
- Do not run `sudo`.
- Do not run `brew upgrade`.
- Do not modify or delete system Python.
- Do not write real API keys into the project.
- Before making changes, list the files planned for creation and modification.
- After making changes, run tests, `git diff --check`, and `git status --short`.
- Do not automatically run `git commit`.
- Do not install dependencies outside the current Sprint.
- Do not implement functionality outside the current Story scope.
