import base64
import random
import string
import json
import time
import uuid
import os
import re

from curl_cffi import requests as curl_requests

from colors import *

import device

from encrypt import encrypt_password_web
from headers import api_headers, gql_headers
from proxies import get_session

from captcha import solve_captcha
from ufac import solve_suspended_captcha
from utils import find, jazoest, pick_name, deep_find, reg_data, mutation_id

email = ""
full_name = ""
first_name = ""
password = ""
username = ""
month = 6
day = 15
year = 1996
code = ""
tokens = {}
ig_reg_data = ""
session = None
proxyless = True

def bootstrap_device():
    global session
    print_info("[0/5] device bootstrap")
    if proxyless:
        device.proxy_url = ""
        sess = curl_requests.Session(impersonate="chrome")
        sess.get("https://www.instagram.com/", timeout=40)
    else:
        sess = get_session(None)
    headers = device.step1_headers(sess)
    if not headers:
        return False
    session = sess

    print_success("mid " + str(device.device_mid) + " ig_did " + str(device.ig_did))
    return True

def fetch_suggestions(sess):
    got = []
    h = api_headers("https://www.instagram.com/accounts/emailsignup/")
    data = {
        "enc_password": encrypt_password_web(password),
        "email": email,
        "first_name": first_name,
        "username": "",
        "client_id": device.device_mid,
        "seamless_login_enabled": "1",
        "opt_into_one_tap": "false",
    }
    try:
        r = sess.post("https://www.instagram.com/api/v1/web/accounts/web_create_ajax/attempt/", headers=h, data=data, timeout=30)
        body = r.json() or {}
        got += [x for x in (body.get("username_suggestions") or []) if x]
        print_info("dry run: " + (r.text or "").replace(chr(10), " "))
    except Exception as e:
        print_warn("dry run suggestions failed: " + str(e))
    for path in ("/api/v1/web/accounts/check_email/", "/api/v1/users/check_email/"):
        try:
            r = sess.post("https://www.instagram.com" + path, headers=api_headers("https://www.instagram.com/accounts/emailsignup/"), data={"device_id": device.device_mid, "email": email}, timeout=30)
            body = r.json() or {}
            got += [x for x in (body.get("username_suggestions") or []) if x]
        except Exception:
            continue
    try:
        r = sess.post("https://www.instagram.com/api/v1/web/accounts/username_suggestions/", headers=api_headers("https://www.instagram.com/accounts/emailsignup/"), data={"email": email, "name": full_name + str(random.randint(1, 99))}, timeout=30)
        got += [x for x in ((r.json() or {}).get("suggestions") or []) if x]
    except Exception:
        pass
    out = []
    for x in got:
        if x not in out:
            out.append(x)
    return out

def signup_tokens(sess):
    global tokens
    print_info("[1/5] reading the signup page tokens")
    h = {"user-agent": device.ua, "accept-language": "pl-PL,pl;q=0.9",
         "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    r = sess.get("https://www.instagram.com/accounts/emailsignup/", headers=h, timeout=40)
    page = r.text or ""
    t = {}
    t["lsd"] = find('"LSD",\\[\\],\\{"token":"([^"]+)"\\}', page)
    t["__rev"] = find('"server_revision":(\\d+)', page)
    t["__hsi"] = find('"hsi":"(\\d+)"', page)
    t["__s"] = find('"__s"\\s*:\\s*"([^"]+)"', page)
    t["__dyn"] = find('"__dyn"\\s*:\\s*"([^"]+)"', page)
    t["__csr"] = find('"__csr"\\s*:\\s*"([^"]+)"', page)
    t["__hsdp"] = find('"__hsdp"\\s*:\\s*"([^"]+)"', page)
    t["__hblp"] = find('"__hblp"\\s*:\\s*"([^"]+)"', page)
    t["__sjsp"] = find('"__sjsp"\\s*:\\s*"([^"]+)"', page)
    t["__hs"] = find('"haste_session":"([^"]+)"', page)
    t["dpr"] = find('"pr":(\\d+)', page, "2")
    t["__spin_r"] = find('"__spin_r":(\\d+)', page, t["__rev"])
    t["__spin_b"] = find('"__spin_b":"([^"]+)"', page, "trunk")
    t["__spin_t"] = find('"__spin_t":(\\d+)', page, str(int(time.time())))
    t["__d"] = "www"
    t["__user"] = "0"
    t["__a"] = "1"
    t["__req"] = "1b"
    t["__ccg"] = "GOOD"
    t["__comet_req"] = "7"
    t["__crn"] = "comet.igweb.PolarisCAAIGRegistrationHomepageRoute"
    if not t["lsd"]:
        print_warn("no lsd token in the page (graphql will probably be refused)")
    else:
        print_success("lsd " + t["lsd"] + " rev " + str(t["__rev"]) +
           " dyn " + ("yes" if t["__dyn"] else "no") +
           " csr " + ("yes" if t["__csr"] else "no"))
    tokens = t
    return bool(t["lsd"])

def gql_post(sess, data, friendly, referer):
    data = dict(data)
    data["jazoest"] = jazoest(device.ig_did or "0")
    for key in ("av", "__d", "__user", "__a", "__req", "__ccg", "dpr", "__comet_req",
                "__crn", "__spin_r", "__spin_b", "__spin_t", "__rev", "__hsi",
                "__hs", "__hsdp", "__hblp", "__s", "__sjsp"):
        if tokens.get(key):
            data.setdefault(key, tokens[key])
    r = sess.post("https://www.instagram.com/api/graphql", headers=gql_headers(referer, friendly, tokens), data=data, timeout=60)
    body = (r.text or "").strip().removeprefix("for (;;);").strip()
    try:
        return r, json.loads(body)
    except Exception:
        return r, {}

def caa_submit(sess):
    global ig_reg_data
    print_info("[2/5] CAA form submit")
    waterfall = str(uuid.uuid4())
    variables = {"input": {
        "client_mutation_id": mutation_id(),
        "actor_id": "0",
        "machine_id": device.device_mid or "",
        "reg_data": reg_data(day, month, year, email, full_name, password, username),
        "sk_pipa_consent_given": False,
        "waterfall_id": waterfall,
    }}
    data = {
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "useCAARegistrationFormSubmitMutation",
        "server_timestamps": "true",
        "variables": json.dumps(variables, separators=(",", ":")),
        "doc_id": "25782408224726258",
        "qpl_active_flow_ids": "175125627",
        "fb_api_analytics_tags": json.dumps(["qpl_active_flow_ids=175125627"]),
    }
    if tokens.get("lsd"):
        data["lsd"] = tokens["lsd"]
    r, obj = gql_post(sess, data, "useCAARegistrationFormSubmitMutation",
                      "https://www.instagram.com/accounts/emailsignup/?next=")
    body = json.dumps(obj)
    if not obj:
        print_error("non-JSON answer: " + (r.text or ""))
        return False, ""
    node = (obj.get("data") or {}).get("caa_registration_homepage_submit") or {}
    status = node.get("status") or (obj.get("data") or {}).get("useCAARegistrationFormSubmitMutation", {}).get("status")
    persist = node.get("captcha_persist_data") or (node.get("errors") or {}).get("captcha_persist_data")
    if status == "SUCCESS":
        ntf = deep_find(obj, "ntf_context")
        raw = deep_find(obj, "ig_reg_data")
        ig_reg_data = ""
        if isinstance(ntf, str) and ntf:
            ig_reg_data = ntf
        elif isinstance(raw, str) and raw:
            ig_reg_data = raw
        elif isinstance(raw, dict):
            ig_reg_data = raw.get("ntf_context") or ""
        if not ig_reg_data:
            m = re.search(r'"ig_reg_data"\s*:\s*"([^"]+)"', json.dumps(obj))
            if m:
                ig_reg_data = m.group(1)
        print_warn("no captcha requested by IG (soft-block branch)")
        print_success("CAA submit SUCCESS" + (" (ig_reg_data " + str(ig_reg_data) + ")" if ig_reg_data else ""))
        if not ig_reg_data:
            print_error("SUCCESS but no ig_reg_data found - dump in /tmp/ig_caa_submit.json")
            return False, ""
        return True, ""
    if persist:
        print_warn("captcha required (captcha_persist_data " + str(persist) + ")")
        return False, persist
    print_info("status: " + str(status))
    if obj.get("errors"):
        print_error("errors: " + str(obj.get("errors")))
    print_error("no success and no captcha: " + body)
    return False, ""

def captcha_submit(sess, persist, captcha_token):
    global ig_reg_data
    print_info("[3/5] submitting the solved captcha")
    variables = {"input": {
        "actor_id": "0",
        "client_mutation_id": mutation_id(),
        "access_flow_version": "pre_mt_behavior",
        "captcha_persist_data": persist,
        "captcha_response": captcha_token,
        "cipher": "",
        "ig_search_query": "",
        "index": 10,
        "machine_id": device.device_mid or "",
        "next_uri": None,
        "password": {"sensitive_string_value": ""},
        "recover_method": "",
        "reg_data": reg_data(day, month, year, email, full_name, password, username),
        "source": "CAA_IG_REGISTRATION",
    }, "scale": 2}
    data = {
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "useCAASubmitReCaptchaActionMutation",
        "server_timestamps": "true",
        "variables": json.dumps(variables, separators=(",", ":")),
        "doc_id": "25344249978604116",
        "qpl_active_flow_ids": "175125627",
        "fb_api_analytics_tags": json.dumps(["qpl_active_flow_ids=175125627"]),
    }
    if tokens.get("lsd"):
        data["lsd"] = tokens["lsd"]
    r, obj = gql_post(sess, data, "useCAASubmitReCaptchaActionMutation",
                      "https://www.instagram.com/accounts/emailsignup/?next=")
    data_all = obj.get("data") or {}
    node = (data_all.get("caa_submit_recaptcha_action")
            or data_all.get("useCAASubmitReCaptchaActionMutation") or {})
    ig_reg_data = deep_find(obj, "ig_reg_data")
    if not ig_reg_data:
        resp = node.get("caa_registration_response") or {}
        ig_reg_data = (resp.get("ig_reg_data") or resp.get("registration_data")
                       or resp.get("context") or "")
    if not ig_reg_data:
        resp = node.get("caa_registration_response") or {}
        if node.get("is_success") and resp:
            ig_reg_data = json.dumps(resp, separators=(",", ":"))
    if not ig_reg_data:
        print_error("captcha submit failed: " + json.dumps(obj))
        return False
    print_success("captcha accepted, ig_reg_data " + str(ig_reg_data))
    return True

def confirm_code(sess):
    global ig_reg_data
    print_info("[4/5] confirming the email code")
    token = ig_reg_data
    if isinstance(token, dict):
        token = token.get("ntf_context") or ""
    if not isinstance(token, str) or not token:
        print_error("no ig_reg_data token for the confirmation")
        return False
    payload = {
        "client_mutation_id": mutation_id(),
        "actor_id": "0",
        "conf_code": {"sensitive_string_value": str(code).strip()},
        "ig_reg_data": token,
        "machine_id": device.device_mid or "",
        "sk_pipa_consent_given": False,
        "youth_consent_decision_time": None,
    }
    data = {
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "useCAAFBConfirmationFormSubmitMutation",
        "server_timestamps": "true",
        "variables": json.dumps({"input": payload}, separators=(",", ":")),
        "doc_id": "24050931851170558",
    }
    if tokens.get("lsd"):
        data["lsd"] = tokens["lsd"]
    r, obj = gql_post(sess, data, "useCAAFBConfirmationFormSubmitMutation",
                      "https://www.instagram.com/accounts/emailsignup/?next=")
    node = (obj.get("data") or {}).get("xfb_caa_registration_confirmation_submit") or {}
    if node.get("user_id") or node.get("created_user_id"):
        print_success("confirmed: user_id " + str(node.get("user_id") or node.get("created_user_id")) +
           " username " + str(node.get("username")))
        ck = dict(sess.cookies.items())
        ck.update(dict(r.cookies))
        for name in ("sessionid", "ds_user_id", "csrftoken"):
            if not ck.get(name) and sess.cookies.get(name):
                ck[name] = sess.cookies.get(name)
        if ck.get("sessionid"):
            save(ck)
        return True
    if obj.get("errors"):
        e = (obj.get("errors") or [{}])[0]
        desc = str(e.get("description") or e.get("message") or "")
        print_warn(desc + "(code " + str(e.get("code")) + ")")
        if "wygas" in desc or "nieprawid" in desc:
            print_error("that address already has a pending/older code - use a never-used address")
    ck = dict(sess.cookies.items())
    ck.update(dict(r.cookies))
    for name in ("sessionid", "ds_user_id"):
        if not ck.get(name) and sess.cookies.get(name):
            ck[name] = sess.cookies.get(name)
    if ck.get("sessionid") and ck.get("ds_user_id"):
        print_success("session established")
        save(ck)
        return True
    return False

def save(cookies):
    d = os.path.join("output", "register")
    if not os.path.isdir(d):
        os.makedirs(d)
    path = os.path.join(d, "web_accounts.ini")

    line = ("+instagram=web," + email + "," + password + "," + first_name + ",0," +
            base64.b64encode(json.dumps(dict(cookies)).encode()).decode() + "," + username + ",")

    f = open(path, "a")
    f.write(line + "\n")
    f.close()
    print_success("saved to output/register/web_accounts.ini")
    print_info("sessionid : " + str(cookies.get("sessionid")))
    print_info("ds_user_id: " + str(cookies.get("ds_user_id")))
    print()
    print_success("now turn it into a mobile token:")
    print_info("python3 ../login.py " + username + " --password '" + password + "' --phase1")

def main():
    global email, full_name, first_name, password, username, month, day, year, code, session

    print()
    print_info(bold("INSTAGRAM CREATOR"), autocolor=colors.PURPLE)
    print()

    email = input("email address: ").strip()
    if not email:
        print_error("an email address is required")
        exit()

    first_name, last_name = pick_name()
    full_name = first_name + " " + last_name
    password = (
        "".join(random.choice(string.ascii_letters) for _ in range(8)) +
        str(random.randint(100, 999)) + "!")
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    year = random.randint(1996, 2004)

    code = ""

    print_info("email    : " + color(email, colors.LIGHT_GRAY))
    print_info("name     : " + color(full_name, colors.LIGHT_GRAY))
    print_info("password : " + color(password, colors.LIGHT_GRAY))
    print_info("birthday : " + color("%d/%d/%d" % (month, day, year), colors.LIGHT_GRAY))
    print()

    if not bootstrap_device():
        print_error("device bootstrap failed")
        exit()
    if not signup_tokens(session):
        print_error("could not read the page tokens")
        exit()
    if proxyless:
        print_info("connection: direct (proxyless) exit " + device.exit_ip(session))
    elif device.proxy_url:
        print_info("connection: proxy " + str(device.proxy_url).split("@")[-1] +
                   " exit " + device.exit_ip(session))
    else:
        print_info("connection: direct (no proxy)")

    choices = fetch_suggestions(session)
    if choices:
        username = random.choice(choices)
        print_info("username : " + color(username, colors.LIGHT_GRAY) +
                   "(random of " + str(len(choices)) + " suggestions)")
    else:
        username = re.sub("[^a-z0-9]", "", full_name.lower()) + str(random.randint(1000, 99999))
        print_warn("no suggestions returned, generated handle " + username)
        print_info("username : " + color(username, colors.LIGHT_GRAY))

    success, persist = caa_submit(session)
    if not success and not persist:
        print_error("caa submit failed and no captcha was offered")
        exit()
    if not persist:
        print_error("IG issued no captcha: this exit is soft-blocked (no account can be created)")
        print_error("rotate the exit or use a proxy pool with fresh IPs, then retry")
        exit()
    captcha_token = solve_captcha(proxyless)
    if not captcha_token:
        print_error("no captcha token - cannot continue")
        exit()
    if not captcha_submit(session, persist or "", captcha_token):
        print_error("captcha action rejected - no account created")
        exit()

    ck = dict(session.cookies.items())
    for name in ("sessionid", "ds_user_id"):
        v = session.cookies.get(name)
        if v:
            ck[name] = v
    if ck.get("sessionid") and ck.get("ds_user_id"):
        print_success("account created (session cookies present, email code not needed)")
        save(ck)
        print()
        solve_suspended_captcha(session)
        print_success("done")
        return
    print_info("no session cookies yet - continuing to the email code")

    print_warn("[5/5] enter the email code")
    if not code:
        code = input("email verification code: ").strip()
    if not code:
        print_error("a verification code is required")
        exit()
    if not confirm_code(session):
        exit()

    solve_suspended_captcha(session)
    print_success("done")

if __name__ == "__main__":
    main()
