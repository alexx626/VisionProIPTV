"""No production keys or customer data: all signatures use an ephemeral test key."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from licensing_protocol import PRODUCT, b64encode, verify_entitlement

private = Ed25519PrivateKey.generate()
public = b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
now = 1800000000

def sign(payload):
    raw = b64encode(json.dumps(payload, separators=(',', ':')).encode())
    return 'VP1.' + raw + '.' + b64encode(private.sign(('VP1.' + raw).encode()))

base = dict(version=1, product=PRODUCT, email='test@example.com', kind='lifetime', issued_at=now)
token = sign(base)
assert verify_entitlement(token, ' Test@Example.com ', public, now=now)['kind'] == 'lifetime'
def rejects(token, **kwargs):
    try:
        verify_entitlement(token, kwargs.pop('email', 'test@example.com'), public, now=kwargs.pop('now', now), **kwargs)
    except ValueError:
        return
    raise AssertionError('Invalid entitlement was accepted')
rejects(token, email='someone@example.com')
rejects(token[:-4] + 'AAAA')
rejects(sign(dict(base, product='different-product')))
rejects(sign(dict(base, issued_at=now + 3600)))
trial = sign(dict(base, kind='trial', expires_at=now + 60 * 86400, installation_id='test-device'))
assert verify_entitlement(trial, 'test@example.com', public, 'test-device', now=now + 59 * 86400)
rejects(trial, installation_id='test-device', now=now + 60 * 86400)
rejects(trial, installation_id='another-device')
rejects(sign(dict(base, kind='trial', expires_at=now + 61 * 86400, installation_id='test-device')), installation_id='test-device')
print('PASS: signed lifetime and 60-day trial; tamper, email, product, clock, device and expiry checks')
