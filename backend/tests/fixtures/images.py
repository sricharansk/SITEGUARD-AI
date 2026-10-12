"""Synthetic image fixtures for vision tests. Generated in memory; no real site photos are used."""

import io
import struct
import zlib

from PIL import Image, ImageDraw, ImageFilter


def _encode(img: Image.Image, fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


def site_photo(width: int = 960, height: int = 720, fmt: str = "JPEG") -> bytes:
    """A well-lit, sharp, textured scene: passes every image-quality check."""
    img = Image.new("RGB", (width, height), (120, 130, 140))
    draw = ImageDraw.Draw(img)
    for x in range(0, width, 40):
        for y in range(0, height, 40):
            shade = 60 + ((x // 40 + y // 40) % 2) * 120
            draw.rectangle([x, y, x + 39, y + 39], fill=(shade, shade - 20, shade + 20))
    draw.line([(0, height // 2), (width, height // 3)], fill=(250, 220, 30), width=6)
    return _encode(img, fmt)


def dark_photo() -> bytes:
    img = Image.new("RGB", (960, 720), (12, 12, 14))
    ImageDraw.Draw(img).rectangle([100, 100, 300, 300], fill=(25, 25, 25))
    return _encode(img, "JPEG")


def blurred_photo() -> bytes:
    img = Image.open(io.BytesIO(site_photo())).filter(ImageFilter.GaussianBlur(6))
    return _encode(img, "JPEG")


def flat_tiny_photo() -> bytes:
    """Small, uniform, featureless: low resolution, low contrast and possibly blurred."""
    return _encode(Image.new("RGB", (320, 240), (128, 128, 128)), "PNG")


def rotated_with_metadata() -> bytes:
    """A 600x400 JPEG whose EXIF says 'rotate 90 degrees' (orientation 6) and that carries a GPS tag."""
    img = Image.open(io.BytesIO(site_photo(600, 400)))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation
    exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0)}  # GPS IFD: must not survive preprocessing
    return _encode(img, "JPEG", exif=exif.tobytes())


def png_bomb(width: int = 20_000, height: int = 20_000) -> bytes:
    """A tiny PNG whose header claims a huge canvas (a decompression bomb)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 64)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
