# Working in this repo

## Keep it short

Comments and commit messages are read by people in a hurry.

- **Comments** say *why*, in 1–2 lines, never more than 4. No history, no
  investigation story, no restating the code.
- **Commit subject** ≤ 65 characters. **Body** ≤ 8 lines: what changed and
  why, in plain sentences.
- **Docstrings**: one line, plus a short paragraph only if needed.
- **PR bodies**: a few bullets.

`tools/check_brevity.py` enforces the numbers at push time.

## Also

- `git config core.hooksPath tools/hooks` once per clone.
- Use `python3 tools/gh_gate.py` instead of `gh` for every GitHub write.
