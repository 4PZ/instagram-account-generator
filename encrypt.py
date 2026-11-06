import time

from base64 import b64encode
from struct import pack
from Crypto.Cipher import AES
from nacl.utils import random as nacl_random
from nacl.public import PublicKey, SealedBox

def encrypt_password_web(plaintext):
    ts = int(time.time())
    key = nacl_random(32)
    cipher = AES.new(key, AES.MODE_GCM, nonce=b"\x00" * 12, mac_len=16)
    cipher.update(str(ts).encode("utf-8"))
    ct, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))

    pub = bytes.fromhex("8dd9aad29d9a614c338cff479f850d3ec57c525c33b3f702ab65e9e057fc087e")
    sealed = SealedBox(PublicKey(pub)).encrypt(key)
    blob = pack("<BB", 1, 87) + pack("<h", len(sealed)) + sealed + tag + ct
    return "#PWD_INSTAGRAM_BROWSER:9:" + str(ts) + ":" + b64encode(blob).decode("utf-8")
