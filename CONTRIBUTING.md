# Contributing

## Pull requests are not being accepted yet

This is an initial public release and Mindgard is not taking outside code
contributions at this stage. Pull requests will be closed unmerged — not
because they are unwelcome in spirit, but because accepting them without a
contributor licence agreement in place would leave the copyright position
unclear, and the project is AGPL-3.0 licensed by a single copyright holder.

**Bug reports, security reports and feature requests are very welcome** —
please open an issue. See [SECURITY.md](SECURITY.md) for anything
security-sensitive.

If a CLA is put in place later, this section will say so.

## Setup

```bash
git clone --recurse-submodules https://github.com/Mindgard/prompt-injection-studio
cd prompt-injection-studio
uv sync --all-extras
```

`uv sync` on its own gives a bare-user environment (base package plus dev
tools), where the optional-generator tests skip — useful for checking a minimal
install still works. `--all-extras` installs everything so nothing skips.

## Before opening a PR

```bash
uv run ruff check pistudio tests
uv run ruff format pistudio tests
uv run pytest -q
```

Everything must pass, with no warnings. Under `--all-extras` a small number of
skips is expected — they are guarded on things a full install cannot supply
(an absent optional backend, or a lossy-by-construction encoding covered
elsewhere) and each states its reason with `pytest -rs`.

## Building

```bash
uv build       # wheel + sdist into dist/
uv publish     # needs UV_PUBLISH_TOKEN
```

The wheel has to carry all bundled package data — the carrier audio and the
example payload files. CI asserts this, because losing it breaks the audio
examples in a way the test suite alone would not catch.

Run `uv lock` when dependencies change, and commit the lockfile.

## Guidelines

- **Keep the base install light.** A new generator that needs a third-party
  package belongs behind an extra. Import it lazily *inside* the writer
  function and raise via `_check_dep()` so `pistudio file list` still works
  without it. `tests/test_extras_degrade.py` enforces this.
- **Don't reflow payload text.** Payload and conversation strings are data.
  The files holding them are exempt from `E501` for that reason.
- **Test behaviour, not implementation.** Cover the error paths too — a
  missing device, a malformed payload, an absent dependency.
- **Device-side code goes in its own repository.** `pistudio/hardware/`
  holds the host side only; firmware and on-device apps live in the
  `vendor/` submodules.

## Adding a file format

1. Write the writer in `pistudio/files/formats/writers_ext.py` with the
   signature `(text: str, path: str) -> None`.
2. Register a `FileFormat` in `registry_ext.py`, setting `requires` (the pip
   package) and `group` (the extra it belongs to).
3. Declare the extra in `pyproject.toml` if it is new.
4. Add a test.

## Scope

This is an offensive security tool for authorised testing. Contributions
that only add evasion of defensive controls, or that target systems
indiscriminately, will be declined.
