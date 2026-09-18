#!/usr/bin/env python3
"""Break each security control in turn and assert a test catches it.

A green suite only means nothing *currently* contradicts a control. This proves
each one is actually covered: it patches the source to disable a control, runs
the suite, and fails if the suite still passes.

    uv run python scripts/verify_controls.py

If you move or rename a control this script fails until you update it. That is
deliberate — it cannot rot into a no-op the way a test can.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pistudio_mcp"


@dataclass(frozen=True)
class Mutation:
    """One control, disabled by a textual substitution in its module."""

    control: str
    module: str
    before: str
    after: str


MUTATIONS = (
    Mutation(
        control="identifier validation rejects option-injection and traversal",
        module="security.py",
        before='or not _IDENTIFIER_RE.fullmatch(value)\n        or ".." in value',
        after="or False",
    ),
    Mutation(
        control="output paths are confined to the output directory",
        module="security.py",
        before="if resolved != root and root not in resolved.parents:",
        after="if False:",
    ),
    Mutation(
        control="absolute output paths are refused",
        module="security.py",
        before="if candidate.is_absolute():",
        after="if False:",
    ),
    Mutation(
        control="secrets are masked in free text",
        module="security.py",
        before="    for pattern in _SECRET_VALUE_RES:\n        text = pattern.sub(REDACTED, text)",
        after="    pass",
    ),
    Mutation(
        control="a secret-named key masks its whole subtree",
        module="security.py",
        before="in_secret=in_secret or bool(isinstance(k, str) and _SECRET_KEY_RE.search(k))",
        after="in_secret=in_secret",
    ),
    Mutation(
        control="untrusted results carry the do-not-act notice",
        module="security.py",
        before='block.setdefault("notice", UNTRUSTED_NOTICE)',
        after="pass",
    ),
    Mutation(
        control="only a command's verb path is logged or echoed",
        module="security.py",
        before='return redact_text(" ".join(argv[:3]))',
        after='return redact_text(" ".join(argv))',
    ),
    Mutation(
        control="the audit log refuses to follow a symlink",
        module="security.py",
        before="os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600",
        after="os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600",
    ),
    Mutation(
        control="the subprocess never reads stdin",
        module="cli.py",
        before="stdin=subprocess.DEVNULL,",
        after="",
    ),
    Mutation(
        control="the child environment is an allowlist",
        module="cli.py",
        before="env = {k: v for k, v in source.items() if k in allowed or k.startswith(_ENV_ALLOW_PREFIX)}",
        after="env = dict(source)",
    ),
    Mutation(
        control="device credentials are dropped without the hardware opt-in",
        module="cli.py",
        before="    if not hardware:\n        for var in _DEVICE_CREDENTIAL_VARS:\n            env.pop(var, None)",
        after="    pass",
    ),
    Mutation(
        control="a JSON payload is never taken from stderr",
        module="cli.py",
        before="    data = _json_payload(proc.stdout) if json_output else None",
        after="    data = _json_payload(proc.stdout or proc.stderr) if json_output else None",
    ),
    Mutation(
        control="per-call timeouts are clamped to a ceiling",
        module="cli.py",
        before="return max(1.0, min(float(timeout), _MAX_TIMEOUT))",
        after="return float(timeout)",
    ),
    Mutation(
        control="read-only mode blocks state changes",
        module="server.py",
        before="    if _READONLY:\n        raise PiStudioMCPError(",
        after="    if False:\n        raise PiStudioMCPError(",
    ),
    Mutation(
        control="ngrok publishing is gated behind an opt-in",
        module="server.py",
        before="if ngrok and not _NGROK_ENABLED:",
        after="if False:",
    ),
    Mutation(
        control="hardware delivery is gated behind an opt-in",
        module="server.py",
        before="    if not _HW_ENABLED:\n        raise PiStudioMCPError(",
        after="    if False:\n        raise PiStudioMCPError(",
    ),
    Mutation(
        control="side-effecting actions are rate-limited",
        module="budget.py",
        before="if len(_timestamps) >= _MAX_PER_HOUR:",
        after="if False:",
    ),
)


def _run_suite() -> bool:
    """True if the test suite passes."""
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "-x", "-q", "--no-cov", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def main() -> int:
    if not _run_suite():
        print("The suite fails before any mutation — fix that first.")
        return 1
    print(f"Baseline green. Checking {len(MUTATIONS)} controls.\n")

    uncovered: list[str] = []
    for mutation in MUTATIONS:
        target = SRC / mutation.module
        original = target.read_text()
        if mutation.before not in original:
            print(f"  STALE   {mutation.control}")
            print(f"          (pattern not found in {mutation.module} — update this script)")
            uncovered.append(f"{mutation.control} [stale]")
            continue

        backup = Path(tempfile.mkdtemp()) / mutation.module
        shutil.copy2(target, backup)
        try:
            target.write_text(original.replace(mutation.before, mutation.after, 1))
            still_green = _run_suite()
        finally:
            shutil.copy2(backup, target)

        if still_green:
            print(f"  GAP     {mutation.control}")
            uncovered.append(mutation.control)
        else:
            print(f"  covered {mutation.control}")

    if uncovered:
        print(f"\n{len(uncovered)} control(s) not covered by a failing test:")
        for control in uncovered:
            print(f"  - {control}")
        return 1
    print(f"\nAll {len(MUTATIONS)} controls are covered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
