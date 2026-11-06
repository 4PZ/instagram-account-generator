import device

def api_headers(referer):
    h = {
        "authority": "www.instagram.com",
        "accept": "*/*",
        "accept-language": "pl-PL,pl;q=0.9",
        "accept-encoding": "gzip, deflate, br, zstd",
        "content-type": "application/x-www-form-urlencoded",
        "dpr": "2",
        "origin": "https://www.instagram.com",
        "referer": referer,
        "sec-ch-prefers-color-scheme": "light",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
        "sec-ch-ua-full-version-list": "",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": '""',
        "sec-ch-ua-platform": '"macOS"',
        "sec-ch-ua-platform-version": '""',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": device.ua,
        "viewport-width": "1728",
        "x-asbd-id": "359341",
        "x-csrftoken": device.csrf_token,
        "x-ig-app-id": "936619743392459",
        "x-ig-www-claim": "0",
        "x-instagram-ajax": "1034262494",
        "x-requested-with": "XMLHttpRequest",
        "priority": "u=1, i",
        "cookie": ("dpr=2; csrftoken=" + device.csrf_token + "; mid=" + device.device_mid +
                   "; ig_nrcb=1; ig_cb=1; ig_did=" + device.ig_did + "; datr=" + device.datr +
                   "; rur=ASH"),
        "x-mid": device.device_mid,
        "x-web-device-id": device.ig_did,
    }
    return h

def bootstrap_headers(kind, mid, did, csrf):
    base = {
        "Host": "graphql.instagram.com" if kind == "activate" else "www.instagram.com",
        "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Model": '""',
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Ch-Ua-Platform-Version": '""',
        "Sec-Ch-Ua-Full-Version-List": "",
        "User-Agent": device.ua,
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-Ch-Prefers-Color-Scheme": "light",
        "X-Asbd-Id": "359341",
        "X-Ig-App-Id": "936619743392459",
        "X-Csrftoken": csrf,
        "Priority": "u=1, i",
    }
    if kind == "activate":
        base.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Fb-Friendly-Name": "PolarisCookieMutation",
            "Accept": "*/*",
            "Origin": "https://www.instagram.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://www.instagram.com/",
        })
    elif kind == "shared":
        base.update({
            "X-Mid": mid,
            "X-Web-Device-Id": did,
            "X-Ig-Www-Claim": "0",
            "X-Requested-With": "XMLHttpRequest",
            "Dpr": "2",
            "Viewport-Width": "1728",
            "Accept": "*/*",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://www.instagram.com/accounts/emailsignup/",
        })
    else:
        base.update({
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,image/apng,*/*;q=0.8"),
            "Cache-Control": "max-age=0",
            "Dpr": "2",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
            "Viewport-Width": "1728",
        })
    return base

def gql_headers(referer, friendly, tokens):
    h = {
        "Host": "www.instagram.com",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "X-Csrftoken": device.csrf_token,
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
        "X-Ig-App-Id": "936619743392459",
        "Sec-Ch-Ua-Model": '""',
        "X-Asbd-Id": "359341",
        "Sec-Ch-Prefers-Color-Scheme": "light",
        "User-Agent": device.ua,
        "Content-Type": "application/x-www-form-urlencoded",
        "Sec-Ch-Ua-Platform-Version": '""',
        "Sec-Ch-Ua-Full-Version-List": "",
        "Sec-Ch-Ua-Mobile": "?0",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Origin": "https://www.instagram.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "Priority": "u=1, i",
        "X-Fb-Friendly-Name": friendly,
        "X-Fb-Lsd": tokens.get("lsd", ""),
        "X-Mid": device.device_mid,
        "X-Web-Device-Id": device.ig_did,
    }
    return h
