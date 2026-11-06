import hpack

def header_text(value):
    try:
        return value.decode("utf-8", "replace")
    except AttributeError:
        return value

def frames(path):
    preface = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
    data = open(path, "rb").read()
    if data.startswith(preface):
        data = data[len(preface):]
    i = 0
    while i + 9 <= len(data):
        ln = int.from_bytes(data[i:i + 3], "big")
        typ = data[i + 3]
        sid = int.from_bytes(data[i + 5:i + 9], "big") & 0x7FFFFFFF
        pl = data[i + 9:i + 9 + ln]
        if len(pl) < ln:
            break
        yield sid, typ, pl
        i += 9 + ln

def decode_header_block(dec, pending, out):
    try:
        for k, v in dec.decode(bytes(pending[1]), True):
            out.setdefault(pending[0], {})[header_text(k)] = header_text(v)
    except Exception:
        pass

def stream_headers(path):
    preface = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
    dec = hpack.Decoder()
    out = {}
    data = open(path, "rb").read()
    if data.startswith(preface):
        data = data[len(preface):]
    i = 0
    pending = None
    while i + 9 <= len(data):
        ln = int.from_bytes(data[i:i + 3], "big")
        typ = data[i + 3]
        fl = data[i + 4]
        sid = int.from_bytes(data[i + 5:i + 9], "big") & 0x7FFFFFFF
        pl = data[i + 9:i + 9 + ln]
        if len(pl) < ln:
            break
        if typ == 0x1:
            frag = pl
            if fl & 0x8:
                frag = frag[1:]
            if fl & 0x20:
                frag = frag[5:]
            if fl & 0x2:
                try:
                    for k, v in dec.decode(bytes(frag), True):
                        out.setdefault(sid, {})[header_text(k)] = header_text(v)
                except Exception:
                    pass
            else:
                if pending is not None:
                    decode_header_block(dec, pending, out)
                pending = (sid, bytearray(frag))
        elif typ == 0x9 and pending is not None:
            pending[1].extend(pl)
            if fl & 0x2:
                decode_header_block(dec, pending, out)
                pending = None
        else:
            if pending is not None:
                decode_header_block(dec, pending, out)
                pending = None
        i += 9 + ln
    return out

def stream_bodies(path):
    out = {}
    for sid, typ, pl in frames(path):
        if typ == 0 and pl:
            out.setdefault(sid, bytearray()).extend(pl)
    return out
