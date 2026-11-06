import urllib.request
import json

from colors import *

capsolver_key = ""

def capsolver_api(path, payload):
    req = urllib.request.Request("https://api.capsolver.com/" + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def image_to_text(body):
    payload = {"clientKey": capsolver_key, "task": {"type": "ImageToTextTask", "body": body, "module": "common"}}
    try:
        got = capsolver_api("createTask", payload)
    except Exception as e:
        print_error("capsolver image task failed: " + str(e))
        return ""
    if got.get("errorId"):
        print_error("capsolver image task " + str(got.get("errorCode")) + ": " + str(got.get("errorDescription")))
        return ""
    return str((got.get("solution") or {}).get("text") or "").strip()
