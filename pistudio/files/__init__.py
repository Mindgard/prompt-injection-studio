"""Embed — generate files containing prompt injection payloads in various formats.

This module provides file generation capabilities for embedding prompt injection
payloads into 50+ file formats including documents, images, audio, and code files.

Third-Party Attribution
-----------------------
The Anamorpher integration uses Trail of Bits' adversarial image scaling library:

- **Anamorpher Repository**: https://github.com/trailofbits/anamorpher
- **Trail of Bits Blog Post**: https://blog.trailofbits.com/2023/12/04/the-hitchhikers-guide-to-image-scaling-attacks/
- **Trail of Bits Website**: https://www.trailofbits.com/

Anamorpher generates images that appear as a decoy at full resolution but reveal
hidden content when downscaled by AI vision systems.

This integration is not affiliated with or endorsed by Trail of Bits.
"""

from pistudio.files.barcode import (
    BARCODE_TYPES,
    _get_barcode_library,
    list_barcode_types,
    render_barcode_terminal,
    validate_barcode_input,
    write_barcode_png,
    write_barcode_svg,
)

__all__ = [
    "BARCODE_TYPES",
    "_get_barcode_library",
    "list_barcode_types",
    "render_barcode_terminal",
    "validate_barcode_input",
    "write_barcode_png",
    "write_barcode_svg",
]
