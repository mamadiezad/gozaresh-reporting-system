"""RSA-PSS digital signatures for workflow approvals + hash-chained audit log.

Each approver owns an RSA-2048 key pair. Signing a workflow step produces a
detached signature over a canonical JSON payload, so any later mutation of the
report or the step invalidates the signature.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.config import settings

_PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)


def canonical_json(payload: dict[str, Any]) -> bytes:
    """Deterministic serialisation — key order and separators are fixed."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Key management (file keystore; swap for HSM/KMS in production)
# --------------------------------------------------------------------------
def _keystore() -> Path:
    path = Path(settings.KEYSTORE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _key_paths(key_id: str) -> tuple[Path, Path]:
    ks = _keystore()
    return ks / f"{key_id}.pem", ks / f"{key_id}.pub.pem"


def ensure_keypair(key_id: str) -> str:
    """Create the key pair if missing; return the PEM public key."""
    priv_path, pub_path = _key_paths(key_id)
    if not priv_path.exists():
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        priv_path.chmod(0o600)
        pub_path.write_bytes(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    return pub_path.read_text()


def load_public_key_pem(key_id: str) -> str:
    ensure_keypair(key_id)
    return _key_paths(key_id)[1].read_text()


def fingerprint(public_pem: str) -> str:
    return sha256_hex(public_pem.strip())[:32]


# --------------------------------------------------------------------------
# Sign / verify
# --------------------------------------------------------------------------
def sign_payload(key_id: str, payload: dict[str, Any]) -> dict[str, str]:
    ensure_keypair(key_id)
    priv_path, _ = _key_paths(key_id)
    private_key = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    message = canonical_json(payload)
    signature = private_key.sign(message, _PSS, hashes.SHA256())
    return {
        "key_id": key_id,
        "algorithm": "RSA-PSS-SHA256",
        "signature": base64.b64encode(signature).decode(),
        "payload_hash": sha256_hex(message),
        "public_key_fingerprint": fingerprint(load_public_key_pem(key_id)),
        "signed_at": datetime.now(UTC).isoformat(),
    }


def verify_payload(key_id: str, payload: dict[str, Any], signature_b64: str) -> bool:
    _, pub_path = _key_paths(key_id)
    if not pub_path.exists():
        return False
    public_key = serialization.load_pem_public_key(pub_path.read_bytes())
    try:
        public_key.verify(
            base64.b64decode(signature_b64),
            canonical_json(payload),
            _PSS,
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


# --------------------------------------------------------------------------
# Tamper-evident audit chain
# --------------------------------------------------------------------------
GENESIS_HASH = "0" * 64


def chain_hash(previous_hash: str | None, entry: dict[str, Any]) -> str:
    """Blockchain-style linkage: H(prev || canonical(entry))."""
    prev = previous_hash or GENESIS_HASH
    return sha256_hex(prev.encode() + canonical_json(entry))
