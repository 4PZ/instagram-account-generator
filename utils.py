import secrets
import random
import gzip
import os
import re

from encrypt import encrypt_password_web
import zstandard

def decode_body(raw):
    decoders = [gzip.decompress]
    decoders.append(lambda x: zstandard.ZstdDecompressor().decompress(x, max_output_size=8000000))
    decoders.append(lambda x: x)
    for decode in decoders:
        try:
            return decode(raw).decode("utf-8", "replace")
        except Exception:
            pass
    return ""

def sexpr(text):
    pos = 0
    n = len(text)

    def node():
        nonlocal pos
        while pos < n and text[pos] in " \t\r\n":
            pos += 1
        if pos >= n:
            return None
        if text[pos] == "(":
            pos += 1
            items = []
            while True:
                while pos < n and text[pos] in " \t\r\n":
                    pos += 1
                if pos >= n:
                    break
                if text[pos] == ")":
                    pos += 1
                    break
                items.append(node())
            return items
        if text[pos] == '"':
            pos += 1
            buf = []
            while pos < n:
                c = text[pos]
                if c == "\\" and pos + 1 < n:
                    nxt = text[pos + 1]
                    if nxt == "n":
                        buf.append("\n")
                    elif nxt == "t":
                        buf.append("\t")
                    elif nxt == "r":
                        buf.append("\r")
                    else:
                        buf.append(nxt)
                    pos += 2
                    continue
                if c == '"':
                    pos += 1
                    break
                buf.append(c)
                pos += 1
            return "".join(buf)
        j = pos
        while j < n and text[j] not in " \t\r\n()":
            j += 1
        atom = text[pos:j]
        pos = j
        if atom == "true":
            return True
        if atom == "false":
            return False
        if atom == "null":
            return None
        return atom

    return node()

def find(pattern, text, default=""):
    m = re.search(pattern, text)
    if m:
        return m.group(1)
    return default

def jazoest(value):
    total = 0
    for ch in value:
        total += ord(ch)
    return "2" + str(total)

def pick_name():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nameset.txt")
    with open(path, encoding="utf-8", errors="replace") as f:
        pool = [l.strip() for l in f if l.strip()]
    first = random.choice(pool)
    last = random.choice(pool)
    while last == first:
        last = random.choice(pool)
    return first, last

def deep_find(node, key):
    if isinstance(node, dict):
        if node.get(key):
            return node[key]
        for value in node.values():
            got = deep_find(value, key)
            if got:
                return got
    elif isinstance(node, list):
        for value in node:
            got = deep_find(value, key)
            if got:
                return got
    return ""

def reg_data(day, month, year, email, full_name, password, username):
    return {
        "birthday_day": int(day),
        "birthday_month": int(month),
        "birthday_year": int(year),
        "contactpoint": {"sensitive_string_value": email},
        "contactpoint_type": "EMAIL",
        "custom_gender": "",
        "did_use_age": False,
        "firstname": {"sensitive_string_value": ""},
        "fullname": {"sensitive_string_value": full_name},
        "ig_age_block_data": None,
        "lastname": {"sensitive_string_value": ""},
        "preferred_pronoun": None,
        "reg_passwd__": {"sensitive_string_value": encrypt_password_web(password)},
        "sex": None,
        "use_custom_gender": False,
        "username": {"sensitive_string_value": username},
    }

def mutation_id():
    return (secrets.token_hex(4) + "-" + secrets.token_hex(2) + "-" + secrets.token_hex(2) + "-" + secrets.token_hex(2) + "-" + secrets.token_hex(6))
