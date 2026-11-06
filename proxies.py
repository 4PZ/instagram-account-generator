from curl_cffi import requests as curl_requests

import device

def proxy_pool():
    return None

def get_session(px=None):
    device.proxy_url = ""
    s = curl_requests.Session(impersonate="chrome")
    try:
        s.get("https://www.instagram.com/", timeout=40)
    except Exception:
        device.traceback_print()
    return s

def rotate_proxy():
    return getattr(device, "session", None)
