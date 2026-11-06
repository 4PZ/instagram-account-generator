import threading
import json
import time
import os

from curl_cffi import requests as http

api_key = ""
base_url = "https://hero-sms.com/stubs/handler_api.php"
default_service = "ig"
default_country = 0
default_max_price = 0.2
default_interval = 5
default_timeout = 300
default_max_uses = 3
timeout = 30

pool = {}
pool_lock = threading.RLock()
pool_stop = threading.Event()
pool_thread = None
cancel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "herosms_cancel.json")

def api_get(action, **params):
    params["api_key"] = api_key
    params["action"] = action
    try:
        r = http.get(base_url, params=params, timeout=timeout)
        return r.status_code, (r.text or "").strip()
    except Exception as e:
        return 0, str(e)

def parse_json(text):
    try:
        return json.loads(text)
    except Exception:
        return None

def balance():
    status, text = api_get("getBalance")
    if text.startswith("ACCESS_BALANCE:"):
        try:
            return float(text.split(":", 1)[1])
        except Exception:
            return None
    return None

def countries():
    status, text = api_get("getCountries")
    data = parse_json(text)
    if isinstance(data, dict):
        return data
    return {}

def services(country=0, lang="en"):
    status, text = api_get("getServicesList", country=country, lang=lang)
    data = parse_json(text)
    if isinstance(data, dict):
        return data.get("services") or []
    return []

def prices(service=None, country=None):
    params = {}
    if service:
        params["service"] = service
    if country not in (None, 0, "", "0"):
        params["country"] = country
    status, text = api_get("getPrices", **params)
    data = parse_json(text)
    if isinstance(data, dict):
        return data
    return {}

def active():
    status, text = api_get("getActiveActivations")
    data = parse_json(text)
    if isinstance(data, dict):
        return data.get("data") or []
    return []

def best_countries(service=None, max_price=default_max_price, limit=8, prefer_physical=True):
    service = service or default_service
    data = prices(service)
    rows = []
    for country_id, item in data.items():
        if not isinstance(item, dict):
            continue
        info = item.get(service)
        if not isinstance(info, dict):
            continue
        try:
            cost = float(info.get("cost") or 0)
            count = int(info.get("count") or 0)
            physical = int(info.get("physicalCount") or 0)
            cid = int(country_id)
        except Exception:
            continue
        if count <= 0:
            continue
        if max_price is not None and cost > max_price:
            continue
        if prefer_physical:
            rows.append((0 if physical > 0 else 1, cost, -count, cid))
        else:
            rows.append((cost, -count, cid))
    rows.sort()
    return [row[-1] for row in rows[:limit]]

def activation_item(item, service=None, country=None, source=""):
    if not isinstance(item, dict):
        return None
    activation_id = item.get("activationId") or item.get("id")
    phone = item.get("phoneNumber") or item.get("phone") or item.get("number")
    if not activation_id or not phone:
        return None
    phone = str(phone)
    if not phone.startswith("+"):
        phone = "+" + phone
    return {
        "activation_id": str(activation_id),
        "phone_number": phone,
        "phone_raw": str(item.get("phoneNumber") or item.get("phone") or item.get("number")),
        "service": str(item.get("serviceCode") or service or default_service),
        "country": item.get("countryCode") if item.get("countryCode") is not None else country,
        "cost": item.get("activationCost"),
        "can_get_another_sms": bool(item.get("canGetAnotherSms")),
        "expires": item.get("activationEndTime"),
        "source": source,
    }

def parse_activation(text, source="", service=None, country=None):
    text = (text or "").strip()
    if not text:
        return {"error": "EMPTY"}
    if text.startswith("ACCESS_NUMBER:"):
        parts = text.split(":")
        if len(parts) >= 3:
            phone = parts[2]
            if not phone.startswith("+"):
                phone = "+" + phone
            return {
                "activation_id": str(parts[1]),
                "phone_number": phone,
                "phone_raw": parts[2],
                "service": service or default_service,
                "country": country,
                "source": source,
            }
        return {"error": text}
    if text.startswith("{"):
        data = parse_json(text)
        if isinstance(data, dict):
            item = activation_item(data, service, country, source)
            if item:
                return item
            if isinstance(data.get("data"), list) and data["data"]:
                item = activation_item(data["data"][0], service, country, source)
                if item:
                    return item
            if data.get("title"):
                return {"error": str(data.get("title")), "details": data.get("details"), "raw": text}
        return {"error": text}
    if text.startswith("ACCESS_READY"):
        return {"ready": True, "raw": text}
    return {"error": text}

def buy(service=None, country=None, max_price=default_max_price, prefer_physical=True, fallback=True):
    service = service or default_service
    candidates = []
    if country not in (None, 0, "", "0"):
        candidates = [int(country)]
        if fallback:
            for cid in best_countries(service, max_price, prefer_physical=prefer_physical):
                if cid not in candidates:
                    candidates.append(cid)
    else:
        candidates = best_countries(service, max_price, prefer_physical=prefer_physical)
    if not candidates:
        candidates = [0]
    errors = []
    for cid in candidates:
        for action in ("getNumberV2", "getNumber"):
            params = {"service": service, "country": cid}
            if max_price is not None:
                params["maxPrice"] = max_price
            status, text = api_get(action, **params)
            rec = parse_activation(text, action, service, cid)
            if not rec.get("error"):
                rec["status"] = "wait"
                rec["code"] = None
                rec["busy"] = False
                rec["uses"] = 0
                rec["max_uses"] = default_max_uses if rec.get("can_get_another_sms") else 1
                rec["created"] = time.time()
                rec["last_check"] = 0
                rec["raw"] = text
                pool_add(rec)
                return rec
            errors.append(text)
            title = str(rec.get("error"))
            if title in ("NO_BALANCE", "BAD_KEY", "BANNED") or "NO_BALANCE" in text or "BAD_KEY" in text:
                return {"error": title, "errors": errors}
        if not fallback:
            break
    return {"error": errors[-1] if errors else "NO_NUMBERS", "errors": errors}

def extract_code(data):
    if not isinstance(data, dict):
        return ""
    for key in ("sms", "call"):
        item = data.get(key)
        if isinstance(item, dict):
            code = item.get("code") or item.get("text")
            if code:
                return str(code)
    item = data.get("data")
    if isinstance(item, dict):
        code = item.get("code")
        if code:
            return str(code)
        for key in ("sms", "call"):
            sub = item.get(key)
            if isinstance(sub, dict):
                code = sub.get("code") or sub.get("text")
                if code:
                    return str(code)
    if data.get("code"):
        return str(data.get("code"))
    return ""

def status(activation_id, v2=True):
    activation_id = str(activation_id)
    if v2:
        code_status, text = api_get("getStatusV2", id=activation_id)
        if text.startswith("{"):
            data = parse_json(text)
            if isinstance(data, dict) and not data.get("title"):
                code = extract_code(data)
                return {"status": "ok" if code else "wait",
                        "code": code or None, "v2": True, "raw": text, "data": data}
    code_status, text = api_get("getStatus", id=activation_id)
    if text.startswith("STATUS_OK"):
        code = text.split(":", 1)[1].strip() if ":" in text else ""
        return {"status": "ok", "code": code or None, "v2": False, "raw": text}
    if text == "STATUS_WAIT_CODE":
        return {"status": "wait", "code": None, "v2": False, "raw": text}
    if text.startswith("STATUS_WAIT_RETRY") or text.startswith("STATUS_WAIT_RESEND"):
        return {"status": "wait", "code": None, "v2": False, "raw": text}
    if text.startswith("STATUS_CANCEL") or "NOT_FOUND" in text:
        return {"status": "cancel", "code": None, "v2": False, "raw": text}
    return {"status": "raw", "code": None, "v2": False, "raw": text}

def wait_code(activation_id, timeout=default_timeout, interval=default_interval, on_status=None):
    start = time.time()
    while time.time() - start < timeout:
        st = status(activation_id)
        if on_status:
            on_status(st)
        if st.get("code"):
            return st["code"]
        if st.get("status") in ("cancel", "not_found"):
            return None
        time.sleep(interval)
    return None

def set_status(activation_id, value):
    status_code, text = api_get("setStatus", id=str(activation_id), status=value)
    ok = text.startswith("ACCESS") or text == "OK"
    return {"ok": ok, "status": status_code, "raw": text}

def finish(activation_id):
    return set_status(activation_id, 6)

def cancel(activation_id, wait=False):
    result = set_status(activation_id, 8)
    if not result.get("ok") and "EARLY_CANCEL_DENIED" in result.get("raw", ""):
        delay = 120
        data = parse_json(result.get("raw"))
        if isinstance(data, dict):
            try:
                delay = int((data.get("info") or {}).get("minActivationTime") or delay)
            except Exception:
                pass
        if wait:
            time.sleep(delay + 2)
            return set_status(activation_id, 8)
    return result

def reactivate(activation_id, phone=""):
    status_code, text = api_get("reactivate", id=str(activation_id))
    rec = parse_activation(text, "reactivate")
    if rec.get("error") and text.startswith("ACCESS_READY"):
        return {"activation_id": str(activation_id), "phone_number": phone,
                "reused": True, "raw": text}
    if not rec.get("error"):
        rec["reused"] = True
    return rec

def another_sms(activation_id):
    return set_status(activation_id, 3)

def cancel_load():
    try:
        data = json.load(open(cancel_path))
        if isinstance(data, list):
            return set(str(x) for x in data)
    except Exception:
        pass
    return set()

def cancel_save(ids):
    try:
        d = os.path.dirname(cancel_path)
        if not os.path.isdir(d):
            os.makedirs(d)
        tmp = cancel_path + ".tmp"
        f = open(tmp, "w")
        json.dump(sorted(ids), f)
        f.close()
        os.replace(tmp, cancel_path)
    except Exception:
        pass

def cancel_ledger_add(activation_id):
    ids = cancel_load()
    ids.add(str(activation_id))
    cancel_save(ids)

def cancel_ledger_remove(activation_id):
    ids = cancel_load()
    ids.discard(str(activation_id))
    cancel_save(ids)

def pool_add(rec):
    if not rec or rec.get("error"):
        return rec
    aid = str(rec.get("activation_id"))
    rec["activation_id"] = aid
    with pool_lock:
        pool[aid] = rec
    return rec

def pool_get(activation_id):
    with pool_lock:
        rec = pool.get(str(activation_id))
        return dict(rec) if rec else None

def pool_remove(activation_id):
    with pool_lock:
        return pool.pop(str(activation_id), None)

def pool_snapshot():
    with pool_lock:
        return [dict(rec) for rec in pool.values()]

def pool_buy(count=1, service=None, country=None, max_price=default_max_price, prefer_physical=True):
    bought = []
    errors = []
    for _ in range(max(1, int(count))):
        rec = buy(service=service, country=country, max_price=max_price,
                  prefer_physical=prefer_physical)
        if rec.get("error"):
            errors.append(rec.get("error"))
            break
        bought.append(rec)
    return {"bought": bought, "errors": errors}

def pool_take(service=None, country=None, max_price=default_max_price,
              auto_buy=True, timeout=0, prefer_physical=True):
    service = service or default_service
    start = time.time()
    while True:
        with pool_lock:
            for aid, rec in pool.items():
                if rec.get("busy"):
                    continue
                if rec.get("code"):
                    continue
                if rec.get("status") not in ("wait", "ok"):
                    continue
                if service and rec.get("service") and rec["service"] != service:
                    continue
                rec["busy"] = True
                return dict(rec)
        if not auto_buy:
            return {"error": "NO_IDLE_NUMBER"}
        rec = buy(service=service, country=country, max_price=max_price,
                  prefer_physical=prefer_physical)
        if rec.get("error"):
            if timeout and time.time() - start < timeout:
                time.sleep(2)
                continue
            return rec
        if not timeout:
            continue
        if time.time() - start >= timeout:
            return {"error": "TIMEOUT"}

def pool_check(activation_id):
    rec = pool_get(activation_id)
    if not rec:
        return {"error": "NOT_FOUND"}
    st = status(activation_id)
    with pool_lock:
        item = pool.get(str(activation_id))
        if item:
            item["last_check"] = time.time()
            item["status"] = st.get("status")
            if st.get("code"):
                item["code"] = st["code"]
                item["status"] = "ok"
    st["record"] = pool_get(activation_id)
    return st

def pool_wait(activation_id, timeout=default_timeout, interval=default_interval, on_status=None):
    rec = pool_get(activation_id)
    if not rec:
        return None
    if rec.get("code"):
        return rec["code"]
    start = time.time()
    while time.time() - start < timeout:
        st = pool_check(activation_id)
        if on_status:
            on_status(st)
        if st.get("code"):
            return st["code"]
        if st.get("status") == "cancel":
            return None
        time.sleep(interval)
    return None

def pool_clear_code(activation_id):
    with pool_lock:
        rec = pool.get(str(activation_id))
        if rec:
            rec["code"] = None
            rec["status"] = "wait"
    return True

def pool_release(activation_id, success=False, reuse=False, cancel_failed=True):
    rec = pool_get(activation_id)
    if not rec:
        return {"error": "NOT_FOUND"}
    if success:
        result = finish(activation_id)
        pool_remove(activation_id)
        cancel_ledger_remove(activation_id)
        return result
    uses = int(rec.get("uses") or 0)
    max_uses = int(rec.get("max_uses") or 1)
    if reuse and uses + 1 < max_uses:
        result = reactivate(activation_id, rec.get("phone_number", ""))
        if not result.get("error"):
            new_id = str(result.get("activation_id") or activation_id)
            with pool_lock:
                old = pool.pop(str(activation_id), None)
                result["status"] = "wait"
                result["code"] = None
                result["busy"] = False
                result["uses"] = uses + 1
                result["max_uses"] = max_uses
                result["created"] = (old or {}).get("created", time.time())
                result["last_check"] = 0
                pool[new_id] = result
            return result
    if cancel_failed:
        result = cancel(activation_id, wait=False)
        if not result.get("ok") and "EARLY_CANCEL_DENIED" in result.get("raw", ""):
            with pool_lock:
                item = pool.get(str(activation_id))
                if item:
                    item["status"] = "cancel_pending"
                    item["busy"] = False
            cancel_ledger_add(activation_id)
            return result
    pool_remove(activation_id)
    return {"ok": True, "action": "cancelled"}

def pool_sweep():
    out = []
    ids = set()
    for rec in pool_snapshot():
        if rec.get("status") == "cancel_pending":
            ids.add(rec["activation_id"])
    ids |= cancel_load()
    for activation_id in sorted(ids):
        result = cancel(activation_id, wait=False)
        out.append({"activation_id": activation_id, "result": result})
        if result.get("ok") or result.get("status") == 404 or "NOT_FOUND" in result.get("raw", ""):
            pool_remove(activation_id)
            cancel_ledger_remove(activation_id)
    return out

def pool_poll_once(interval=default_interval):
    now = time.time()
    for rec in pool_snapshot():
        if rec.get("code"):
            continue
        if rec.get("status") != "wait":
            continue
        if now - float(rec.get("last_check") or 0) < interval:
            continue
        pool_check(rec["activation_id"])

def pool_poll_loop(interval=default_interval):
    while not pool_stop.wait(interval):
        try:
            pool_poll_once(interval)
        except Exception:
            pass

def pool_start(interval=default_interval):
    global pool_thread
    if pool_thread and pool_thread.is_alive():
        return pool_thread
    pool_stop.clear()
    pool_thread = threading.Thread(target=pool_poll_loop, args=(interval,), daemon=True)
    pool_thread.start()
    return pool_thread

def pool_stop_poller():
    pool_stop.set()
    if pool_thread:
        pool_thread.join(timeout=2)

def pool_stats():
    records = pool_snapshot()
    out = {"total": len(records), "busy": 0, "ready": 0, "waiting": 0,
           "cancel_pending": 0, "spent": 0.0}
    for rec in records:
        if rec.get("busy"):
            out["busy"] += 1
        if rec.get("code"):
            out["ready"] += 1
        if rec.get("status") == "wait":
            out["waiting"] += 1
        if rec.get("status") == "cancel_pending":
            out["cancel_pending"] += 1
        try:
            out["spent"] += float(rec.get("cost") or 0)
        except Exception:
            pass
    return out

get_number = buy
get_number_auto = buy
get_code = wait_code
get_status = status
release_number = pool_release
