# assets

Files the bot serves that are yours rather than the code's.

Put a `qr.png` here and point `UPI_QR_IMAGE=assets/qr.png` at it if you would
rather use your own QR than have the bot generate one. This directory is
mounted into the container, so replacing the file does not need a rebuild.

A static QR carries no amount, so the payer types it in themselves and can send
a different figure from the one they asked the bot for. Setting `UPI_ID` and
letting the bot generate the code avoids that. Run
`python -m scripts.read_qr assets/qr.png` to read the UPI id out of a QR you
already have.
