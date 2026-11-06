import traceback
import random
import json
import time
import re

from colors import *

from headers import api_headers, bootstrap_headers
from params import custom_mid

device_mid = ""
csrf_token = ""
ig_did = ""
datr = ""
proxy_url = ""
ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      " (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")

def traceback_print():
    traceback.print_exc()

def exit_ip(session):
    try:
        r = session.get("https://ifconfig.io/ip", timeout=30)
        return r.text.strip()
    except Exception:
        return "?"

def step1_headers(session):
    global device_mid, csrf_token, ig_did, datr
    print_info("[1/4] generating headers")

    if not device_mid:
        device_mid = custom_mid()
    did = ""
    csrf = ""
    for attempt in range(3):
        try:
            r0 = session.get("https://www.instagram.com/",
                             headers={"user-agent": ua,
                                      "accept-language": "pl-PL,pl;q=0.9",
                                      "accept": ("text/html,application/xhtml+xml,application/xml;"
                                                 "q=0.9,image/avif,image/webp,*/*;q=0.8")},
                             timeout=40)
            page = r0.text or ""
            for marker in (',"device_id":"', '"_js_ig_did"'):
                if marker in page:
                    if marker == ',"device_id":"':
                        did = page.split(marker)[1].split('"')[0]
                    else:
                        m = re.search(marker + '[ \t]*:[ \t]*\\{"value"[ \t]*:[ \t]*"([^"]+)"', page)
                        if m:
                            did = m.group(1)
                    break
            csrf = r0.cookies.get("csrftoken") or csrf
            if not csrf:
                m = re.search('"csrf_token"[ \t]*:[ \t]*"([^"]+)"', page)
                if m:
                    csrf = m.group(1)
            if did and csrf:
                break
        except Exception:
            traceback_print()
        print_warn("attempt " + str(attempt + 1) + ": no ig_did/csrf yet")
        time.sleep(2)
    if not (did and csrf):
        return None
    print_info("ig_did " + did + " csrf " + csrf)

    try:
        act = session.post(
            "https://graphql.instagram.com/graphql/",
            headers=bootstrap_headers("activate", device_mid, did, csrf),
            data={"doc_id": "3810865872362889",
                  "variables": json.dumps({
                      "first_party_tracking_opt_in": True,
                      "ig_did": did,
                      "third_party_tracking_opt_in": True,
                      "input": {"client_mutation_id": 0}})},
            timeout=30)
        ok_act = "\"success\":true" in (act.text or "")
        if ok_act:
            print_success("device activated (PolarisCookieMutation)")
        else:
            print_warn("activation answered: " + (act.text or ""))
    except Exception:
        traceback_print()

    try:
        sd = session.get("https://www.instagram.com/api/v1/web/data/shared_data/",
                         headers=bootstrap_headers("shared", device_mid, did, csrf),
                         timeout=30)
        ck = dict(sd.cookies)
        if ck.get("csrftoken"):
            csrf = ck["csrftoken"]
        if ck.get("mid"):
            device_mid = ck["mid"]
        if ck.get("ig_did"):
            did = ck["ig_did"]
        if sd.cookies.get("datr"):
            datr = sd.cookies.get("datr")
    except Exception:
        traceback_print()
    csrf_token = csrf
    ig_did = did

    try:
        es = session.get("https://www.instagram.com/accounts/emailsignup/",
                         headers=bootstrap_headers("signup", device_mid, did, csrf),
                         timeout=40)
        if not datr:
            datr = es.cookies.get("datr") or datr
        if not datr:
            page2 = es.text or ""
            m = re.search('"_js_datr"[ \t]*:[ \t]*\\{"value"[ \t]*:[ \t]*"([^"]+)"', page2)
            if m:
                datr = m.group(1)
    except Exception:
        traceback_print()
    if not datr:
        datr = "DaHcamJV" + str(random.randint(100000, 999999))
    print_info("mid " + str(device_mid) + " datr " + datr)
    return api_headers("https://www.instagram.com/accounts/emailsignup/")
