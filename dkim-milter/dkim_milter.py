#!/usr/bin/env python3
"""
DKIM signing milter usando dkimpy — Denali PRO SA
"""

import os
import logging
import Milter
import dkim

PRIVATE_KEY_PATH = os.environ.get("DKIM_KEY_PATH", "/etc/dkim/mail.private")
SELECTOR = os.environ.get("DKIM_SELECTOR", "mail").encode()
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8891

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def load_private_key():
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return f.read()

def extract_domain(mailfrom):
    addr = mailfrom.strip().strip('<>').strip()
    if '@' in addr:
        return addr.split('@')[1].lower().encode()
    return None


class DKIMMilter(Milter.Base):
    def __init__(self):
        self.headers = []
        self.body_chunks = []
        self.from_domain = None
        self.raw_message = b""

    def connect(self, IPname, family, hostaddr):
        return Milter.CONTINUE

    def envfrom(self, mailfrom, *args):
        self.headers = []
        self.body_chunks = []
        self.raw_message = b""
        self.from_domain = extract_domain(mailfrom)
        return Milter.CONTINUE

    def header(self, name, hval):
        # Ricostruisce gli header nel formato raw
        self.headers.append(f"{name}: {hval}")
        return Milter.CONTINUE

    def eoh(self):
        return Milter.CONTINUE

    def body(self, chunk):
        self.body_chunks.append(chunk)
        return Milter.CONTINUE

    def eom(self):
        try:
            if not self.from_domain:
                logging.warning("No domain, skipping DKIM signing")
                return Milter.ACCEPT

            private_key = load_private_key()
            domain = self.from_domain

            # Ricostruisce il messaggio completo
            headers_raw = "\r\n".join(self.headers) + "\r\n\r\n"
            body_raw = b"".join(self.body_chunks)
            message = headers_raw.encode() + body_raw

            # Firma con dkimpy
            sig = dkim.sign(
                message,
                SELECTOR,
                domain,
                private_key,
                canonicalize=(b"relaxed", b"simple"),
                signature_algorithm=b"rsa-sha256",
                include_headers=[
                    b"from", b"to", b"subject", b"date", b"message-id"
                ]
            )

            # Estrai il valore della firma (rimuovi "DKIM-Signature: ")
            sig_header = sig.decode()
            if sig_header.startswith("DKIM-Signature:"):
                sig_value = sig_header[len("DKIM-Signature:"):].strip()
                # Rimuovi i line fold
                sig_value = " ".join(sig_value.split())
                self.addheader("DKIM-Signature", sig_value)
                logging.info(f"DKIM signed: s={SELECTOR.decode()} d={domain.decode()}")
            else:
                logging.error(f"Unexpected signature format: {sig_header[:100]}")

        except Exception as e:
            logging.error(f"DKIM signing failed: {e}", exc_info=True)
        return Milter.ACCEPT

    def close(self):
        return Milter.CONTINUE

    def abort(self):
        return Milter.CONTINUE


def main():
    logging.info(f"DKIM milter starting on {LISTEN_HOST}:{LISTEN_PORT}")
    Milter.factory = DKIMMilter
    Milter.set_flags(Milter.ADDHDRS)
    Milter.runmilter("dkim-milter", f"inet:{LISTEN_PORT}@{LISTEN_HOST}", 240)


if __name__ == "__main__":
    main()
