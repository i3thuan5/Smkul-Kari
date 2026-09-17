"""What a Claude Vision input sheet costs, from its PNG header alone.

Standard library only, on purpose. Batching runs on the system python3,
which has neither numpy nor PIL, and `scripts.ocr.sheets` imports both at
module level -- so the batcher cannot import it. The price of a sheet must
still come from one place, or the packer and the batcher drift apart (a
copied 1.10 Mpx budget in a test already did that once). So the numbers
live here and `sheets` imports them.

A PNG's width and height are bytes 16-24: 8 bytes of signature, then the
IHDR chunk's 4-byte length and 4-byte type, then width and height as
big-endian 32-bit integers. Reading those 24 bytes is exact and costs
nothing; opening the image to ask would need PIL.

The three constants belong to somebody else's service -- see the notes in
`sheets.py` above where they used to be. Changing the model, the tier, or
the tool that delivers the image means measuring them again.
"""
import struct

PATCH = 28
LONG_EDGE = 2000
VISUAL_TOKENS = 4784

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path):
    """(width, height) off the header; ValueError if it is not a PNG.

    Never a guess: a wrong size here puts a batch over the cache line
    without anyone seeing it.
    """
    with open(path, "rb") as handle:
        head = handle.read(24)
    if len(head) < 24 or head[:8] != SIGNATURE:
        raise ValueError("%s 不是完整的 PNG 檔頭" % path)
    if head[12:16] != b"IHDR":
        raise ValueError("%s 的 PNG 第一個區塊不是 IHDR" % path)
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def visual_tokens(width, height):
    """Patches the image is charged: ceil(w/28) x ceil(h/28)."""
    return -(-width // PATCH) * -(-height // PATCH)


def tokens(path):
    """Visual tokens of one sheet file."""
    width, height = png_size(path)
    return visual_tokens(width, height)
