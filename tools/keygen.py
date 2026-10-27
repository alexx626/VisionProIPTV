"""VisionPro IPTV license key tool - NEVER ship or commit keys/private.key.

  python tools/keygen.py init                      create keys/private.key + keys/public.key
  python tools/keygen.py issue  <email>            print a lifetime activation code for that email
  python tools/keygen.py verify <email> <code>     check a code against keys/public.key
  python tools/keygen.py list                      show issued codes (keys/issued.log)

The public key printed by `init` must be pasted into PUBLIC_KEY in licensing.py.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
from licensing_protocol import PRODUCT, b64decode, b64encode, normalize_email, verify_entitlement

KEYS = Path(__file__).resolve().parents[1] / 'keys'
PRIVATE, PUBLIC, LOG = KEYS / 'private.key', KEYS / 'public.key', KEYS / 'issued.log'


def load_private():
    if not PRIVATE.is_file():
        sys.exit('keys/private.key missing - run: python tools/keygen.py init')
    return Ed25519PrivateKey.from_private_bytes(b64decode(PRIVATE.read_text().strip()))


def init():
    if PRIVATE.exists():
        sys.exit('keys/private.key already exists - refusing to overwrite (existing codes would stop working).')
    KEYS.mkdir(exist_ok=True)
    private = Ed25519PrivateKey.generate()
    PRIVATE.write_text(b64encode(private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())))
    public = b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    PUBLIC.write_text(public)
    print('Public key (paste into licensing.py PUBLIC_KEY):\n' + public)
    print('Private key saved to', PRIVATE, '- back it up, keep it secret.')


def issue(email):
    email = normalize_email(email)
    private = load_private()
    payload = dict(version=1, product=PRODUCT, email=email, kind='lifetime', issued_at=int(time.time()))
    raw = b64encode(json.dumps(payload, separators=(',', ':')).encode())
    token = 'VP1.' + raw + '.' + b64encode(private.sign(('VP1.' + raw).encode()))
    verify_entitlement(token, email, PUBLIC.read_text().strip())
    with LOG.open('a', encoding='utf-8') as log:
        log.write(f'{datetime.now():%Y-%m-%d %H:%M}\t{email}\t{token}\n')
    print('Email:', email)
    print('Activation code:\n' + token)
    return token


def verify(email, token):
    data = verify_entitlement(token, email, PUBLIC.read_text().strip())
    print('VALID:', data)


def list_issued():
    print(LOG.read_text(encoding='utf-8') if LOG.is_file() else '(no codes issued yet)')


if __name__ == '__main__':
    commands = {'init': init, 'issue': issue, 'verify': verify, 'list': list_issued}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]](*sys.argv[2:])
