import urllib.parse
import base64
import json
import time
import re

from colors import *

import device
import herosms
from capsolver import image_to_text

def ufac_ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return None

def ufac_cookies(sess):
    out = []
    seen = set()
    for name, value in sess.cookies.items():
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "value": value,
                    "domain": ".instagram.com", "path": "/"})
    return out

def ufac_open(sess):
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(user_agent=device.ua, locale="en-US",
                                  viewport={"width": 1280, "height": 900})
    context.add_cookies(ufac_cookies(sess))
    page = context.new_page()
    got = []

    def on_response(resp):
        try:
            if "async/wbloks/fetch" not in resp.url or "checkpoint.ufac" not in resp.url:
                return
            if resp.request.method != "POST":
                return
            text = resp.text()
            got.append({"url": resp.url, "body": resp.request.post_data or "",
                        "text": text, "status": resp.status,
                        "error": '"payload":null' in text})
        except Exception:
            pass

    page.on("response", on_response)
    url = ("https://www.instagram.com/accounts/suspended/"
           "?next=https%3A%2F%2Fwww.instagram.com%2Faccounts%2Fonetap%2F%3F__coig_ufac%3D1")
    entry = None
    for _ in range(3):
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        for _ in range(25):
            for item in reversed(got):
                if not item["error"]:
                    entry = item
                    break
            if entry:
                break
            page.wait_for_timeout(1000)
        if entry:
            break
        page.wait_for_timeout(3000)
    info = {"playwright": pw, "browser": browser, "context": context,
            "page": page, "entry": entry}
    if got:
        info["last"] = got[-1]
    if not entry:
        if "/accounts/login" in page.url or "checkpoint" in page.url:
            info["login"] = True
        elif "suspended" not in page.url:
            info["done"] = True
    return info

def ufac_strip(text):
    pos = text.find("{")
    if pos < 0:
        return ""
    return text[pos:]

def ufac_stage(text):
    if "contact_point.submit_code" in text:
        return "code"
    if "set_contact_point.submit" in text:
        return "phone"
    if "bot_captcha.submit" in text:
        return "captcha"
    if "complete_intro" in text:
        return "intro"
    if "image_upload" in text or "verification selfie" in text:
        return "selfie"
    if '"/allowed' in text or "allowed?__coig_ufac" in text:
        return "done"
    return "unknown"

def ufac_bits(text):
    apps = ("complete_intro", "bot_captcha.submit", "set_contact_point.submit",
            "contact_point.submit_code")
    pos = max(text.rfind(app) for app in apps)
    chunk = text[pos:pos + 2200] if pos >= 0 else text[:2200]
    head = chunk
    at = chunk.find("server_params")
    if at >= 0:
        head = chunk[at:at + 900]
    euds = re.findall(r'\(eud (\d{10,})\)', head)
    root = euds[0] if euds else ""
    instance = euds[-1] if euds else ""
    persisted = ""
    m = re.search(r'persisted_data[^A-Za-z0-9_-]{1,80}([A-Za-z0-9_-]{40,})', head)
    if m:
        persisted = m.group(1)
    if not persisted:
        m = re.search(r'(AZ[0-9A-Za-z_-]{60,})', head)
        if m:
            persisted = m.group(1)
    return {"root": root, "persisted": persisted, "instance": instance}

def ufac_app_bits(text, app):
    pos = text.rfind(app)
    if pos < 0:
        return {"root": "", "instance": ""}
    chunk = text[pos:pos + 1600]
    at = chunk.find("server_params")
    head = chunk[at:at + 900] if at >= 0 else chunk
    euds = re.findall(r'\(eud (\d{10,})\)', head)
    return {"root": euds[0] if euds else "",
            "instance": euds[-1] if euds else ""}

def ufac_image(text):
    m = re.search(r'https:\\/\\/www\.facebook\.com\\/captcha\\/tfbimage\\/[^"]*?captcha_challenge_hash=[A-Za-z0-9_-]+', text)
    if m:
        return m.group(0).replace("\\/", "/")
    m = re.search(r'https://www\.facebook\.com/captcha/tfbimage/[^"]*?captcha_challenge_hash=[A-Za-z0-9_-]+', text)
    return m.group(0) if m else ""

def ufac_url(base, appid):
    parts = urllib.parse.urlsplit(base)
    query = []
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        if key == "appid":
            value = appid
        elif key == "type":
            value = "action"
        query.append((key, value))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                    urllib.parse.urlencode(query), parts.fragment))

def ufac_params(base, obj):
    inner = json.dumps(obj, separators=(",", ":"))
    outer = json.dumps({"params": inner}, separators=(",", ":"))
    out = []
    for key, value in urllib.parse.parse_qsl(base, keep_blank_values=True):
        if key == "params":
            value = outer
        out.append((key, value))
    return urllib.parse.urlencode(out)

def ufac_fetch(page, url, body):
    try:
        text = page.evaluate("""async (a) => {
            const r = await fetch(a[0], {method: 'POST', credentials: 'include',
                headers: {'content-type': 'application/x-www-form-urlencoded;charset=UTF-8'},
                body: a[1]});
            return await r.text();
        }""", [url, body])
    except Exception as e:
        print_error("ufac fetch failed: " + str(e))
        return ""
    return text

def solve_suspended_captcha(sess):
    activation_id = ""
    sms_success = False
    code_done = False
    try:
        info = ufac_open(sess)
    except Exception as e:
        print_error("suspended flow failed: " + str(e))
        return ""
    try:
        if info.get("login"):
            print_error("session expired or checkpointed")
            return ""
        if info.get("done"):
            print_success("account is not suspended")
            return "ok"
        entry = info.get("entry")
        if not entry:
            last = info.get("last")
            if last:
                print_error("ufac controller returned: " + str(last["status"]) +
                            " " + ufac_strip(last["text"])[:300])
            else:
                print_error("could not capture the ufac controller request")
            print_info("page: " + info["page"].url)
            try:
                open("/tmp/ufac_fail.html", "w").write(info["page"].content())
            except Exception:
                pass
            return ""
        base_url = entry["url"]
        base_body = entry["body"]
        text = entry["text"]
        print_info("[5/5] ufac stage: " + ufac_stage(ufac_strip(text)))
        m = re.search(r'(?:SMS|WhatsApp) to (\+?\d+)', ufac_strip(text))
        phone = m.group(1) if m else ""
        tries = 0
        phone_tries = 0
        code_tries = 0
        last = ""
        while True:
            stage = ufac_stage(ufac_strip(text))
            if stage == "done":
                print_success("ufac challenge cleared")
                break
            if stage == "selfie":
                print_success("phone verified; identity selfie required")
                sms_success = True
                return "selfie"
            if stage == "unknown":
                if last == "code":
                    print_info("code response has no known action - verifying")
                    break
                print_warn("unknown ufac stage")
                print_info(ufac_strip(text)[:600])
                return ""
            last = stage
            bits = ufac_bits(ufac_strip(text))
            if not bits["root"] or not bits["instance"]:
                print_error("could not read the ufac challenge state")
                return ""
            if stage == "intro":
                obj = {"server_params": {
                           "challenge_root_id": bits["root"],
                           "INTERNAL__latency_qpl_marker_id": 36707139,
                           "INTERNAL__latency_qpl_instance_id": bits["instance"]}}
            elif stage == "captcha":
                tries += 1
                if tries > 50:
                    print_error("captcha retries exhausted")
                    return ""
                img = ufac_image(ufac_strip(text))
                answer = ""
                if img:
                    print_info("captcha image: " + img)
                    for _ in range(3):
                        try:
                            r = info["context"].request.get(img, timeout=30000,
                                headers={"referer": "https://www.instagram.com/"})
                            if r.ok:
                                open("/tmp/ufac_captcha.png", "wb").write(r.body())
                                print_info("captcha saved to /tmp/ufac_captcha.png")
                                raw = image_to_text(base64.b64encode(r.body()).decode())
                                answer = re.sub(r"[^A-Za-z0-9]", "", raw)
                                print_info("captcha ocr: " + raw + " -> " + answer)
                                if re.match(r"^[A-Za-z0-9]{4,8}$", answer):
                                    break
                            else:
                                print_warn("captcha image status " + str(r.status))
                        except Exception as e:
                            print_warn("captcha image failed: " + str(e))
                        time.sleep(2)
                if not re.match(r"^[A-Za-z0-9]{4,8}$", answer):
                    print_warn("captcha ocr invalid, refreshing")
                    rb = ufac_app_bits(ufac_strip(text), "refresh_ufac_state")
                    if rb["root"] and rb["instance"]:
                        obj = {"server_params": {
                                   "challenge_root_id": rb["root"],
                                   "INTERNAL__latency_qpl_marker_id": 36707139,
                                   "INTERNAL__latency_qpl_instance_id": rb["instance"]}}
                        url = ufac_url(base_url, "com.bloks.www.checkpoint.ufac.refresh_ufac_state")
                        body = ufac_params(base_body, obj)
                        text = ufac_fetch(info["page"], url, body)
                        print_info("ufac refresh: " + str(len(text)) + " bytes")
                        continue
                    print_error("could not refresh the captcha")
                    return ""
                obj = {"server_params": {
                           "persisted_data": bits["persisted"],
                           "challenge_root_id": bits["root"],
                           "INTERNAL__latency_qpl_marker_id": 36707139,
                           "INTERNAL__latency_qpl_instance_id": bits["instance"]},
                       "client_input_params": {"captcha_response": answer}}
            elif stage == "phone":
                phone_tries += 1
                if phone_tries > 3:
                    print_error("phone retries exhausted")
                    return ""
                if activation_id:
                    herosms.pool_release(activation_id, success=False)
                    activation_id = ""
                phone = ""
                rec = herosms.pool_take(service="ig", max_price=0.05)
                if rec.get("error"):
                    print_warn("herosms: " + str(rec.get("error")))
                else:
                    activation_id = rec.get("activation_id") or ""
                    phone = rec.get("phone_number") or ""
                    print_info("herosms number: " + phone + " (" +
                               str(rec.get("country")) + ", " + str(rec.get("cost")) + ")")
                if not phone:
                    phone = ufac_ask("phone number (with +country code): ")
                if phone is None or not phone:
                    return ""
                if not phone.startswith("+"):
                    phone = "+" + phone
                obj = {"server_params": {
                           "challenge_root_id": bits["root"],
                           "medium": "sms",
                           "INTERNAL__latency_qpl_marker_id": 36707139,
                           "INTERNAL__latency_qpl_instance_id": bits["instance"]},
                       "client_input_params": {"contact_point": phone,
                                               "use_existing_contact_point": 0}}
            else:
                code_tries += 1
                if code_tries > 4:
                    print_error("code retries exhausted")
                    return ""
                if not phone:
                    m = re.search(r'(?:SMS|WhatsApp) to (\+?\d+)', ufac_strip(text))
                    phone = m.group(1) if m else ""
                answer = ""
                if activation_id and not code_done:
                    print_info("waiting for the sms code on " + phone)
                    answer = herosms.pool_wait(activation_id, timeout=300)
                    if answer:
                        herosms.pool_clear_code(activation_id)
                        print_info("sms code: " + answer)
                if not answer:
                    answer = ufac_ask("code sent to " + phone + " (enter to resend): ")
                if answer is None:
                    return ""
                if not answer:
                    rb = ufac_app_bits(ufac_strip(text), "contact_point.resend_code")
                    if rb["root"] and rb["instance"]:
                        obj = {"server_params": {
                                   "challenge_root_id": rb["root"],
                                   "send_by_whatsapp": False,
                                   "was_sent_by_whatsapp": False,
                                   "INTERNAL__latency_qpl_marker_id": 36707139,
                                   "INTERNAL__latency_qpl_instance_id": rb["instance"]}}
                        url = ufac_url(base_url, "com.bloks.www.checkpoint.ufac.contact_point.resend_code")
                        body = ufac_params(base_body, obj)
                        text = ufac_fetch(info["page"], url, body)
                        print_info("ufac resend: " + str(len(text)) + " bytes")
                        continue
                    return ""
                obj = {"server_params": {
                           "challenge_root_id": bits["root"],
                           "show_toast": False,
                           "INTERNAL__latency_qpl_marker_id": 36707139,
                           "INTERNAL__latency_qpl_instance_id": bits["instance"]},
                       "client_input_params": {"captcha_code": answer}}
            app = {"intro": "com.bloks.www.checkpoint.ufac.complete_intro",
                   "captcha": "com.bloks.www.checkpoint.ufac.bot_captcha.submit",
                   "phone": "com.bloks.www.checkpoint.ufac.set_contact_point.submit",
                   "code": "com.bloks.www.checkpoint.ufac.contact_point.submit_code"}[stage]
            url = ufac_url(base_url, app)
            body = ufac_params(base_body, obj)
            text = ufac_fetch(info["page"], url, body)
            print_info("ufac " + stage + ": " + str(len(text)) + " bytes")
            if stage == "code":
                code_done = True
                if activation_id:
                    herosms.pool_clear_code(activation_id)
            if not text:
                return ""
            if '"payload":null' in ufac_strip(text):
                print_error("ufac " + stage + " rejected: " + ufac_strip(text)[:240])
                return ""
        try:
            info["page"].goto("https://www.instagram.com/accounts/onetap/?__coig_ufac=1",
                              wait_until="domcontentloaded", timeout=60000)
            info["page"].wait_for_timeout(3000)
            print_info("final url: " + info["page"].url)
            if "suspended" in info["page"].url:
                print_error("still suspended")
                return ""
        except Exception as e:
            print_warn("verify failed: " + str(e))
        sms_success = True
        print_success("account unsuspended")
        return "ok"
    finally:
        if activation_id:
            try:
                herosms.pool_release(activation_id, success=sms_success)
            except Exception as e:
                print_warn("herosms release failed: " + str(e))
        try:
            info["browser"].close()
            info["playwright"].stop()
        except Exception:
            pass
