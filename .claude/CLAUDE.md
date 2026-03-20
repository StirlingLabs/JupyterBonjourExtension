# Project Instructions

Do the correct thing, not the simplest thing; minimal patches now that fail to deal with structural issues only create higher maintenance cost in the future. 

Tasks are not complete until lint & typecheck is clean `ruff check --fix` and `ty check` will let you know about any issues you need to fix.  Run tests with `uv run pytest`.

Defensive programming is important; the common case should always be the default and "falling back" should always require an active measure; it should not be able to happen by forgetting a parameter.
