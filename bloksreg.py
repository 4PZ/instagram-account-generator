import urllib.parse
import secrets
import base64
import glob
import json
import os

from h2 import frames, stream_headers, stream_bodies
from utils import decode_body, sexpr

__all__ = ["raw_dir", "dkc_pairs", "bundle_strings", "all_dkc_pairs",
           "bloks_server_params", "bloks_reg_context", "bloks_states",
           "request_params", "capture_requests", "app_capture_request",
           "app_response_text", "app_state", "attestation_key_hash",
           "zca_key_hash", "newest_zca", "newest_proof", "app_attest_params",
           "fetch_attest_params"]

def raw_dir():
    return os.environ.get("IG_RAWCAP") or "/tmp/rawcap"

def dkc_pairs(tree, out):
    if not isinstance(tree, list):
        return out
    for i, child in enumerate(tree):
        if (isinstance(child, list) and child and child[0] == "dkc"
                and all(isinstance(x, str) for x in child[1:])
                and i + 1 < len(tree) and isinstance(tree[i + 1], list)
                and tree[i + 1] and tree[i + 1][0] == "dkc"):
            keys = child[1:]
            vals = tree[i + 1][1:]
            if len(keys) == len(vals):
                out.append(dict(zip(keys, vals)))
    for child in tree:
        dkc_pairs(child, out)
    return out

def bundle_strings(response_text):
    out = []
    try:
        outer = json.loads(response_text)
    except Exception:
        return [response_text]
    data = outer.get("data") if isinstance(outer, dict) else None
    node = None
    if isinstance(data, dict):
        for k, v in data.items():
            if k.startswith("1$bloks_action"):
                node = v
                break
    if node is None:
        return []
    try:
        bundle = node["action"]["action_bundle"]["bloks_bundle_action"]
    except Exception:
        return []
    if isinstance(bundle, str):
        try:
            bundle = json.loads(bundle)
        except Exception:
            return []
    stack = [bundle]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
        elif isinstance(cur, str):
            out.append(cur)
    return out

def all_dkc_pairs(response_text):
    pairs = []
    for s in bundle_strings(response_text):
        try:
            tree = sexpr(s)
        except Exception:
            continue
        if tree is None:
            continue
        pairs.extend(dkc_pairs(tree, []))
    return pairs

def bloks_server_params(response_text):
    best = {}
    best_score = None
    for pair in all_dkc_pairs(response_text):
        score = (1 if "reg_info" in pair else 0,
                 1 if "reg_context" in pair else 0,
                 1 if "current_step" in pair else 0,
                 len(pair))
        if best_score is None or score > best_score:
            best_score = score
            best = pair
    return best

def bloks_reg_context(response_text):
    rc = bloks_server_params(response_text).get("reg_context")
    if isinstance(rc, str):
        return rc
    return ""

def bloks_states(response_text):
    out = []
    for pair in all_dkc_pairs(response_text):
        if "state" in pair and "exception_category" in pair:
            out.append(pair)
    return out

def request_params(body_text):
    try:
        form = {k: v[0] for k, v in urllib.parse.parse_qs(body_text).items()}
        env = json.loads(form["variables"])
        inner = json.loads(json.loads(env["params"]["params"])["params"])
    except Exception:
        return {}
    sp = inner.get("server_params") or {}
    ri = sp.get("reg_info")
    if isinstance(ri, str):
        try:
            ri = json.loads(ri)
        except Exception:
            ri = {}
    return {"client_input_params": inner.get("client_input_params") or {},
            "server_params": sp, "reg_info": ri or {}}

def capture_requests(only_registration=True):
    out = []
    for path in sorted(glob.glob(os.path.join(raw_dir(), "*_c2s.bin")), key=os.path.getmtime):
        if os.path.basename(path).startswith("replay"):
            continue
        try:
            hdrs = stream_headers(path)
            bods = stream_bodies(path)
        except Exception:
            continue
        for sid in sorted(bods):
            body = decode_body(bytes(bods[sid]))
            friendly = ""
            try:
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
                friendly = form.get("fb_api_req_friendly_name", "")
            except Exception:
                pass
            if only_registration and "caa" not in friendly:
                continue
            req = {"file": path, "stream": sid, "headers": hdrs.get(sid, {}),
                   "body": body, "friendly": friendly}
            req.update(request_params(body))
            out.append(req)
    return out

def app_capture_request(aac_value):
    candidates = []
    for req in capture_requests():
        ci = req.get("client_input_params") or {}
        if not ci.get("aac"):
            continue
        if aac_value and ci.get("aac") != aac_value:
            continue
        candidates.append(req)
    best = None
    chosen = None
    for req in reversed(candidates):
        if best is None:
            best = req
        text = app_response_text(req["file"], req["stream"])
        if not text:
            continue
        params = bloks_server_params(text)
        if "reg_info" in params:
            chosen = req
            break
    if chosen is None:
        chosen = best
    if chosen is None:
        return {}
    ci = chosen.get("client_input_params") or {}
    sp = chosen.get("server_params") or {}
    ri = chosen.get("reg_info") or {}
    id_keys = ("device_id", "family_device_id", "qe_device_id", "ig4a_qe_device_id",
               "machine_id", "waterfall_id")

    def pick(src):
        out = {}
        for key in id_keys:
            val = src.get(key)
            if val:
                out[key] = val
        return out

    ids = pick(ci)
    for key, val in pick(sp).items():
        ids.setdefault(key, val)
    for key, val in pick(ri).items():
        ids.setdefault(key, val)
    return {"headers": chosen["headers"], "ids": ids, "friendly": chosen["friendly"],
            "file": chosen["file"], "stream": chosen["stream"], "body": chosen["body"],
            "client_input_params": ci, "server_params": sp, "reg_info": ri,
            "ids_ci": pick(ci), "ids_sp": pick(sp), "ids_ri": pick(ri)}

def app_response_text(path, stream):
    s2c = path[:-8] + "_s2c.bin"
    if not os.path.exists(s2c):
        return ""
    buf = bytearray()
    for sid, typ, pl in frames(s2c):
        if sid == stream and typ == 0 and pl:
            buf.extend(pl)
    return decode_body(bytes(buf))

def app_state(aac_value):
    req = app_capture_request(aac_value)
    if not req and aac_value:
        req = app_capture_request(aac_value.rstrip("\\"))
    if not req:
        return {}
    ids = dict(req["ids"])
    client_machine = ""
    for other in capture_requests():
        ci = other.get("client_input_params") or {}
        if ci.get("machine_id"):
            client_machine = ci["machine_id"]
    if client_machine:
        ids["client_machine_id"] = client_machine
    state = {"headers": req["headers"], "ids": ids, "friendly": req["friendly"],
             "server_params": req.get("server_params") or {},
             "ids_ci": req.get("ids_ci") or {}, "ids_sp": req.get("ids_sp") or {},
             "ids_ri": req.get("ids_ri") or {}}
    tid = state["server_params"].get("text_input_id") or ""
    if isinstance(tid, str) and ":" in tid:
        state["text_input_prefix"] = tid.split(":")[0]
        try:
            state["text_input_counter"] = int(tid.split(":")[1])
        except Exception:
            state["text_input_counter"] = 0
    text = app_response_text(req["file"], req["stream"])
    params = bloks_server_params(text)
    ri = params.get("reg_info")
    if isinstance(ri, str):
        try:
            ri = json.loads(ri)
        except Exception:
            ri = {}
    state["reg_info"] = ri or {}
    state["reg_context"] = params.get("reg_context") or ""
    state["current_step"] = params.get("current_step")
    return state

def attestation_key_hash():
    for path in sorted(glob.glob(os.path.join(raw_dir(), "*_c2s.bin")),
                       key=os.path.getmtime, reverse=True):
        try:
            bods = stream_bodies(path)
        except Exception:
            continue
        for sid in sorted(bods):
            body = decode_body(bytes(bods[sid]))
            if "key_hash=" not in body or "app_scoped_device_id=" not in body:
                continue
            try:
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
            except Exception:
                continue
            if form.get("key_hash"):
                return form["key_hash"]
    return secrets.token_hex(32)

def zca_key_hash(zca):
    try:
        raw = base64.b64decode(zca + "=" * ((4 - len(zca) % 4) % 4))
        j = json.loads(raw)
        return j["android"]["aka"].get("keyHash", "")
    except Exception:
        return ""

def newest_zca():
    best = ""
    for path in sorted(glob.glob(os.path.join(raw_dir(), "*_c2s.bin")), key=os.path.getmtime):
        if os.path.basename(path).startswith("replay"):
            continue
        try:
            hdrs = stream_headers(path)
        except Exception:
            continue
        for h in hdrs.values():
            z = h.get("x-meta-zca")
            if z and z != best:
                best = z
    return best

def newest_proof():
    out = {}
    for path in sorted(glob.glob(os.path.join(raw_dir(), "*_c2s.bin")), key=os.path.getmtime):
        if os.path.basename(path).startswith("replay"):
            continue
        try:
            hdrs = stream_headers(path)
        except Exception:
            continue
        for h in hdrs.values():
            for key in ("x-meta-zca", "x-meta-usdid"):
                val = h.get(key)
                if val:
                    out[key] = val
    return out

def app_attest_params(zca_key_hash_value=""):
    ks_nonce = ""
    ks_time = 0
    ks_hash = ""
    pi = []
    for path in sorted(glob.glob(os.path.join(raw_dir(), "*_c2s.bin")), key=os.path.getmtime):
        if os.path.basename(path).startswith("replay"):
            continue
        try:
            hdrs = stream_headers(path)
            bods = stream_bodies(path)
        except Exception:
            continue
        for sid in sorted(bods):
            url = (hdrs.get(sid, {}) or {}).get(":path", "")
            if "attestation" not in url:
                continue
            body = decode_body(bytes(bods[sid]))
            key_hash = ""
            try:
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
                key_hash = form.get("key_hash", "")
            except Exception:
                pass
            text = app_response_text(path, sid)
            if not text:
                continue
            try:
                nonce = (json.loads(text) or {}).get("challenge_nonce") or ""
            except Exception:
                nonce = ""
            if not nonce:
                continue
            stamp = os.path.getmtime(path)
            if "keystore" in url:
                if zca_key_hash_value and key_hash != zca_key_hash_value:
                    continue
                if stamp >= ks_time:
                    ks_nonce = nonce
                    ks_time = stamp
                    ks_hash = key_hash
            elif "playintegrity" in url:
                pi.append((stamp, nonce))
    pi_nonce = ""
    for stamp, nonce in pi:
        if stamp <= ks_time + 5:
            pi_nonce = nonce
    if not pi_nonce and pi:
        pi_nonce = pi[-1][1]
    if not ks_nonce and not pi_nonce:
        return ""
    items = []
    if ks_nonce:
        items.append({"version": 2, "type": "keystore", "errors": [-1013],
                      "challenge_nonce": ks_nonce, "signed_nonce": "", "key_hash": ""})
    if pi_nonce:
        items.append({"version": 3, "type": "play_integrity", "errors": [-2],
                      "challenge_nonce": pi_nonce, "integrity_token": ""})
    return json.dumps({"attestation": items}, separators=(",", ":"))

def fetch_attest_params(session, device_id, key_hash):
    if not device_id:
        return ""
    ua = ("Instagram 451.0.0.53.80 Android (33/13; 489dpi; 1344x2992; Genymobile/Google; "
          "Pixel 8 Pro; motion_phone_arm64; vbox86; en_US; 1089931330)")

    def head(friendly):
        return {"User-Agent": ua,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-IG-App-ID": "567067343352427",
                "X-IG-Device-ID": device_id,
                "X-FB-Friendly-Name": friendly,
                "Accept-Encoding": "zstd",
                "X-FB-HTTP-Engine": "Tigon/MNS/TCP",
                "X-IG-Client-Endpoint": "unknown"}

    ks_nonce = ""
    try:
        rv = session.post("https://i.instagram.com/api/v1/attestation/create_android_keystore/",
                          data={"app_scoped_device_id": device_id, "key_hash": key_hash},
                          headers=head("IgApi: attestation/create_android_keystore/"), timeout=30)
        ks_nonce = (rv.json() or {}).get("challenge_nonce") or ""
    except Exception:
        ks_nonce = ""
    pi_nonce = ""
    try:
        rv = session.post("https://i.instagram.com/api/v1/attestation/create_android_playintegrity/",
                          data={"app_scoped_device_id": device_id},
                          headers=head("IgApi: attestation/create_android_playintegrity/"), timeout=30)
        pi_nonce = (rv.json() or {}).get("challenge_nonce") or ""
    except Exception:
        pi_nonce = ""
    if not ks_nonce and not pi_nonce:
        return ""
    items = []
    if ks_nonce:
        items.append({"version": 2, "type": "keystore", "errors": [-1013],
                      "challenge_nonce": ks_nonce, "signed_nonce": "", "key_hash": ""})
    if pi_nonce:
        items.append({"version": 3, "type": "play_integrity", "errors": [-2],
                      "challenge_nonce": pi_nonce, "integrity_token": ""})
    return json.dumps({"attestation": items}, separators=(",", ":"))
