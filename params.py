import base64
import struct
import time
import os

import device

def random_mid():
    head = struct.pack(">I", int(time.time())) + b"\x00\x01\x00\x01"
    return base64.urlsafe_b64encode(head + os.urandom(13)).decode().rstrip("=")

def custom_mid():
    return device.device_mid or random_mid()
