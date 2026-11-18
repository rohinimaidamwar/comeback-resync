import hashlib
import re
import secrets

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
ROUNDS = 210000


def norm_email(s):
    return (s or "").strip().lower()


def valid_email(s):
    return bool(EMAIL.fullmatch(s or ""))


def hash_pw(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ROUNDS)
    return salt.hex() + "$" + h.hex()


def check_pw(pw, stored):
    try:
        salt_hex, hx = stored.split("$", 1)
        h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), ROUNDS)
        return secrets.compare_digest(h.hex(), hx)
    except Exception:
        return False
