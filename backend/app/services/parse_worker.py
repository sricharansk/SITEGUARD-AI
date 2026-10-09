"""Child process for parsing untrusted binary documents (see parsing.parse_document).

Reads the file from stdin, writes {"ok": true, "parser", "pages": [[number, text], ...], "metadata"} or
{"ok": false, "error"} to stdout. Runs under CPU and memory limits set by the parent.
"""

import json
import sys

from app.services.parsing import PARSERS, ParseError


def main() -> None:
    name = sys.argv[1]
    parser = next(p for p in PARSERS if p.name == name)
    content = sys.stdin.buffer.read()
    try:
        doc = parser.parse(content)
        out = {
            "ok": True,
            "parser": doc.parser,
            "pages": [[p.number, p.text] for p in doc.pages],
            "metadata": doc.metadata,
        }
    except ParseError as exc:
        out = {"ok": False, "error": str(exc)}
    except Exception:  # never echo internals; the parent records a generic failure
        out = {"ok": False, "error": "Document could not be read"}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
