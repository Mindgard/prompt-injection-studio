"""Anamorpher integration — adversarial image scaling attacks.

Generates images that look like a decoy (e.g. a cat photo) at full resolution
but reveal a hidden prompt injection payload when downscaled by AI vision
systems.

The attack itself is not ours: this wraps ``anamorpher`` by Trail of Bits
(Kikimora Morozova and Suha Sabi Hussain), Apache-2.0, which is installed into
its own virtualenv and driven as a subprocess.  This module renders the target
image and marshals arguments; anamorpher does the work.

Because anamorpher pins ``numpy>=1.24,<2.0`` while every current
opencv-python requires ``numpy>=2``, installing it into this venv is an
unsolvable resolution -- so the embedding runs in a dedicated Python 3.11
venv (``.anamorpher-venv/``) via subprocess.  The main shell renders the
target payload image locally with Pillow, then delegates the heavy lifting.

Never `pip install anamorpher` into the studio venv; it cannot succeed.

Setup::

    file anamorph setup

Or manually, if the guided flow cannot find a 3.11 interpreter::

    pyenv install 3.11.12  # or any 3.11.x
    ~/.pyenv/versions/3.11.12/bin/python -m venv .anamorpher-venv
    .anamorpher-venv/bin/pip install git+https://github.com/trailofbits/anamorpher.git

See: https://github.com/trailofbits/anamorpher
"""

import contextlib
import json
import logging
import os
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)

# Supported downscaling algorithms
ALGORITHMS = ("nearest", "bicubic", "bilinear")

# Default parameters
DEFAULT_ALGORITHM = "nearest"
DEFAULT_LAMBDA = 0.25
DEFAULT_TARGET_SIZE = (256, 256)

# Trail of Bits credit, shown wherever this generator is named.
ANAMORPHER_REPO = "https://github.com/trailofbits/anamorpher"
ANAMORPHER_BLOG = "https://blog.trailofbits.com/2025/08/21/weaponizing-image-scaling-against-production-ai-systems/"
ANAMORPHER_CREDIT = "anamorpher by Trail of Bits (Apache-2.0)"

# Well-known venv locations (searched in order)
_VENV_SEARCH = (
    ".anamorpher-venv",
    ".venv-anamorpher",
)

# Default venv name created by `file anamorph setup`
DEFAULT_VENV_NAME = ".anamorpher-venv"


def _project_root() -> str:
    """Return the project root directory (parent of pistudio/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _default_venv_dir() -> str:
    """Return the default path for the anamorpher venv."""
    return os.path.join(_project_root(), DEFAULT_VENV_NAME)


def _parse_target_size(size_str: str) -> tuple[int, int]:
    """Parse a ``WxH`` string into a ``(width, height)`` tuple."""
    try:
        parts = size_str.lower().split("x")
        if len(parts) != 2:
            raise ValueError
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Invalid target size '{size_str}'. Expected format: WxH (e.g. 256x256)") from exc


def _find_venv_python() -> str | None:
    """Locate the anamorpher venv Python binary.

    MED-09: Verifies the venv directory lives inside the expected project
    root to prevent symlink-escape attacks.  The python binary itself may
    legitimately symlink to a pyenv/system interpreter outside the tree.
    """
    project_root = os.path.realpath(_project_root())
    for name in _VENV_SEARCH:
        venv_dir = os.path.join(_project_root(), name)
        bin_dir = "Scripts" if sys.platform == "win32" else "bin"
        candidate = os.path.join(venv_dir, bin_dir, "python")
        if os.path.isfile(candidate):
            real_venv = os.path.realpath(venv_dir)
            if not real_venv.startswith(project_root + os.sep) and real_venv != project_root:
                logger.warning("Venv dir resolves outside project root: %s → %s", venv_dir, real_venv)
                continue
            return candidate
    # Also check ANAMORPHER_PYTHON env var for custom locations
    env_python = os.environ.get("ANAMORPHER_PYTHON")
    if env_python and os.path.isfile(env_python):
        return env_python
    return None


# Python script sent to the venv subprocess via -c
_WORKER_SCRIPT = r"""
import json, sys, os
import cv2
import numpy as np

params = json.loads(sys.argv[1])
target_path = params["target_path"]
decoy_path = params["decoy_path"]
output_path = params["output_path"]
algorithm = params["algorithm"]
lam = params["lam"]
tw, th = params["target_size"]

target_img = cv2.imread(target_path)
decoy_img = cv2.imread(decoy_path)

if target_img is None:
    print(json.dumps({"error": f"Failed to load target image: {target_path}"}))
    sys.exit(1)
if decoy_img is None:
    print(json.dumps({"error": f"Failed to load decoy image: {decoy_path}"}))
    sys.exit(1)

target_img = cv2.resize(target_img, (tw, th), interpolation=cv2.INTER_AREA)
decoy_img = cv2.resize(decoy_img, (tw * 4, th * 4), interpolation=cv2.INTER_AREA)

# Import the appropriate generator
# anamorpher installs its modules as `backend/` not `anamorpher/backend/`
try:
    from backend.adversarial_generators.nearest_gen_payload import embed_nn
except ImportError:
    from anamorpher.backend.adversarial_generators.nearest_gen_payload import embed_nn

if algorithm == "nearest":
    result = embed_nn(decoy_img.astype(np.float64), target_img.astype(np.float64), lam=lam)
elif algorithm == "bicubic":
    try:
        from backend.adversarial_generators.bicubic_gen_payload import embed_bicubic
        result = embed_bicubic(decoy_img.astype(np.float64), target_img.astype(np.float64), lam=lam)
    except ImportError:
        result = embed_nn(decoy_img.astype(np.float64), target_img.astype(np.float64), lam=lam)
elif algorithm == "bilinear":
    try:
        from backend.adversarial_generators.bilinear_gen_payload import embed_bilinear
        result = embed_bilinear(decoy_img.astype(np.float64), target_img.astype(np.float64), lam=lam)
    except ImportError:
        result = embed_nn(decoy_img.astype(np.float64), target_img.astype(np.float64), lam=lam)

result = np.clip(result, 0, 255).astype(np.uint8)
cv2.imwrite(output_path, result)
print(json.dumps({"ok": True, "path": output_path}))
"""


def write_anamorph(
    text: str,
    path: str,
    *,
    decoy_path: str | None = None,
    algorithm: str = DEFAULT_ALGORITHM,
    lam: float = DEFAULT_LAMBDA,
    target_size: tuple[int, int] = DEFAULT_TARGET_SIZE,
) -> None:
    """Generate an adversarial scaling-attack image.

    The target payload image is rendered locally with Pillow, then the
    actual anamorpher embedding is delegated to a Python 3.11 venv
    subprocess to avoid numpy/opencv version conflicts.

    Parameters
    ----------
    text:
        The prompt injection payload to hide in the image.
    path:
        Output path for the adversarial PNG.
    decoy_path:
        Path to the cover/decoy image.  Required.
    algorithm:
        Downscaling algorithm to target: ``nearest``, ``bicubic``, or
        ``bilinear``.
    lam:
        Mean-preservation weight (0.0–1.0).  Higher values preserve the
        decoy appearance better but may reduce payload fidelity.
    target_size:
        Resolution ``(width, height)`` of the hidden payload image.
    """
    if not decoy_path:
        raise ValueError("--decoy is required for the anamorph format. Provide a cover image path.")

    if algorithm not in ALGORITHMS:
        raise ValueError(f"Unknown algorithm '{algorithm}'. Choose from: {', '.join(ALGORITHMS)}")

    if not os.path.isfile(decoy_path):
        raise FileNotFoundError(f"Decoy image not found: {decoy_path}")

    # Find the anamorpher venv
    venv_python = _find_venv_python()
    if venv_python is None:
        raise ImportError(
            "Anamorpher venv not found. Set up with:\n"
            "  pyenv install 3.11.12\n"
            "  ~/.pyenv/versions/3.11.12/bin/python -m venv .anamorpher-venv\n"
            "  .anamorpher-venv/bin/pip install git+https://github.com/trailofbits/anamorpher.git"
        )

    # Step 1: Render the prompt text as the target (payload) image using Pillow
    from pistudio.files.render_image import render_text_image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        target_path = tmp.name
    try:
        render_text_image(text, target_path, fmt="png")

        # Step 2: Delegate to the venv subprocess
        params = json.dumps(
            {
                "target_path": os.path.abspath(target_path),
                "decoy_path": os.path.abspath(decoy_path),
                "output_path": os.path.abspath(path),
                "algorithm": algorithm,
                "lam": lam,
                "target_size": list(target_size),
            }
        )

        result = subprocess.run(
            [venv_python, "-c", _WORKER_SCRIPT, params],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            msg = stderr or stdout or "Unknown error"
            raise RuntimeError(f"Anamorpher subprocess failed:\n{msg}")

        # Parse output
        try:
            output = json.loads(result.stdout.strip())
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"Unexpected anamorpher output: {result.stdout.strip()}") from exc

        if "error" in output:
            raise RuntimeError(output["error"])

        if not os.path.isfile(path):
            raise RuntimeError(f"Anamorpher did not produce output file: {path}")

    finally:
        with contextlib.suppress(OSError):
            os.unlink(target_path)
