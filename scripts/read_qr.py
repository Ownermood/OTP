"""Read the UPI id out of a QR image you already have.

Most people have a QR from their bank or payment app but do not know the VPA
behind it. This prints it, so it can go into ``UPI_ID`` and the bot can
generate codes with the amount already filled in.

    python -m scripts.read_qr assets/qr.png
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def decode(path: Path) -> str | None:
    """Return the payload of the QR in ``path``, or ``None`` if none is found."""
    try:
        import cv2
        import numpy
        from PIL import Image
    except ImportError:
        print(
            "This needs the dev extras:\n"
            "    pip install -r requirements-dev.txt\n",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    image = numpy.array(Image.open(io.BytesIO(path.read_bytes())).convert("RGB"))[:, :, ::-1]
    payload, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
    return payload or None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"❌ No such file: {path}", file=sys.stderr)
        return 1

    payload = decode(path)
    if payload is None:
        print("❌ No QR found in that image. Try a sharper or larger screenshot.")
        return 1

    print(f"\nQR contents:\n  {payload}\n")

    if not payload.lower().startswith("upi://"):
        print("⚠️  That is not a UPI QR, so there is no UPI id in it.")
        return 1

    params = {k: v[0] for k, v in parse_qs(urlparse(payload).query).items()}
    vpa = params.get("pa")
    if not vpa:
        print("⚠️  This UPI QR carries no payee address.")
        return 1

    print("Put this in your .env:\n")
    print(f"    UPI_ID={vpa}")
    if params.get("pn"):
        print(f"    UPI_PAYEE_NAME={params['pn']}")
    if params.get("am"):
        print(
            f"\n⚠️  This QR has a fixed amount of {params['am']}. The bot generates a "
            "fresh code per request, so that fixed amount will not be used."
        )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
