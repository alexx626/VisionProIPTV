"""Signed entitlement verification shared by local and hosted activation flows.

Only the public verification key belongs in the distributed application.
This module does not generate or contain customer signing keys.
"""
import base64
import json
import re
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

PRODUCT = 'visionpro-iptv-standard'
TRIAL_DAYS = 60


def normalize_email(email):
    email = email.strip().casefold()
    if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise ValueError('Enter a valid email address.')
    return email


def b64decode(text):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', text):
        raise ValueError('Invalid activation code.')
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def b64encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def verify_entitlement(token, email, public_key, installation_id='', now=None):
    """Fail closed on malformed, altered, expired, wrong-email or wrong-product codes."""
    if not isinstance(token, str) or len(token) > 8192:
        raise ValueError('Invalid activation code.')
    now = int(time.time() if now is None else now)
    try:
        prefix, payload, signature = token.strip().split('.')
        if prefix != 'VP1':
            raise ValueError()
        raw = b64decode(payload)
        Ed25519PublicKey.from_public_bytes(b64decode(public_key)).verify(
            b64decode(signature), b'VP1.' + payload.encode('ascii'))
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('product') != PRODUCT or data.get('version') != 1:
            raise ValueError()
        if data.get('email') != normalize_email(email):
            raise ValueError('The code belongs to a different email address.')
        if not isinstance(data.get('issued_at'), int) or data['issued_at'] > now + 300:
            raise ValueError()
        if data.get('kind') == 'trial':
            expires = data.get('expires_at')
            if not isinstance(expires, int) or not data['issued_at'] < expires <= data['issued_at'] + TRIAL_DAYS * 86400:
                raise ValueError()
            if not installation_id or data.get('installation_id') != installation_id:
                raise ValueError()
            if now >= expires:
                raise ValueError('The 60-day trial has expired.')
        elif data.get('kind') == 'lifetime':
            if data.get('expires_at') is not None:
                raise ValueError()
        else:
            raise ValueError()
        return data
    except (InvalidSignature, TypeError, UnicodeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid activation code.') from exc
    except ValueError as exc:
        if str(exc) in ('Enter a valid email address.', 'The code belongs to a different email address.', 'The 60-day trial has expired.'):
            raise
        raise ValueError('Invalid activation code.') from exc
