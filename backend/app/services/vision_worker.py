"""Child process that decodes an untrusted image (see vision.prepare_image).

Reads the file from stdin and writes {"ok": true, ...} with the oriented size, image-quality measurements and a
re-encoded JPEG without metadata (base64), or {"ok": false, "error"}. Runs under CPU and memory limits set by the
parent. argv: <expected format JPEG|PNG> <max pixels> <max side>.
"""

import base64
import io
import json
import sys
import warnings


def measure(img) -> dict:
    """Simple, deterministic image-quality measurements on a small greyscale copy."""
    from PIL import ImageFilter, ImageStat

    grey = img.convert("L")
    grey.thumbnail((512, 512))
    stat = ImageStat.Stat(grey)
    w, h = grey.size
    # The edge filter marks the image border as an edge, so measure the interior only.
    edges = ImageStat.Stat(grey.filter(ImageFilter.FIND_EDGES).crop((1, 1, max(2, w - 1), max(2, h - 1))))
    return {
        "mean_luminance": round(stat.mean[0], 1),
        "contrast": round(stat.stddev[0], 1),
        "sharpness": round(edges.stddev[0], 1),
    }


def prepare(content: bytes, expected: str, max_pixels: int, max_side: int) -> dict:
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = max_pixels
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    try:
        img = Image.open(io.BytesIO(content))
        fmt = img.format
        if fmt != expected:
            return {"ok": False, "error": "Image content does not match its file type"}
        img.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return {"ok": False, "error": f"Image exceeds {max_pixels} pixels"}
    exif = img.getexif()
    had_metadata = bool(exif) or bool(img.info.get("icc_profile")) or "exif" in img.info
    original_size = img.size
    oriented = ImageOps.exif_transpose(img)
    oriented = oriented.convert("RGB")
    quality = measure(oriented)
    width, height = oriented.size
    working = oriented.copy()
    working.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    working.save(buf, format="JPEG", quality=90)  # a fresh encode carries no EXIF or GPS metadata
    return {
        "ok": True,
        "format": fmt,
        "original_size": list(original_size),
        "width": width,
        "height": height,
        "orientation_corrected": oriented.size != original_size or exif.get(0x0112, 1) != 1,
        "metadata_removed": had_metadata,
        "analysis_size": list(working.size),
        "quality": quality,
        "image_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
    }


def main() -> None:
    expected, max_pixels, max_side = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    content = sys.stdin.buffer.read()
    try:
        out = prepare(content, expected, max_pixels, max_side)
    except Exception:  # never echo internals; the parent reports a generic failure
        out = {"ok": False, "error": "Image could not be decoded"}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
