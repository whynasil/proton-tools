#!/usr/bin/env python3
"""Proton signup — CloakBridge: evaluate-only clicks (avoids stale data-hermes-ref)"""
import urllib.request, json, time, random, re, urllib.parse, sys

CB = "http://localhost:9377"
uname = f"faruk{random.randint(1000,9999)}"
pw = "Armada34**"
rec = "lukejimenez4gsh273s@hotmail.com"
print(f"★ {uname}@proton.me")

def post(path, data, timeout=10):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{CB}{path}", data=body, headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
def get(path, timeout=10):
    return json.loads(urllib.request.urlopen(f"{CB}{path}", timeout=timeout).read())
def ev(js):
    return post(f"/tabs/{tid}/evaluate", {"userId":"d","expression":js})
def evf(js):
    return post(f"/tabs/{tid}/evaluate-in-frame", {"userId":"d","expression":js,"frameUrlPrefix":"Name=email"})

# JS helpers
CLICK_BTN = "(function(txt){var b=document.querySelectorAll('button');for(var i=0;i<b.length;i++){if((b[i].textContent||'').includes(txt)){b[i].click();return'clicked';}}return'nf';})"

# Clean
req = urllib.request.Request(f"{CB}/sessions/d", method="DELETE")
try: urllib.request.urlopen(req)
except: pass

tid = post("/tabs", {"userId":"d"})["tabId"]
post(f"/tabs/{tid}/navigate", {"userId":"d","url":"https://account.proton.me/signup?plan=free&language=en"})
time.sleep(5)
print("1) Loaded")

# Fill via evaluate (sequential with blur — React compatible)
ev("(function(){var el=document.getElementById('username');var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;ns.call(el,'" + uname + "');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('blur',{bubbles:true}));return'ok';})()")
time.sleep(1.5)
ev("(function(){var el=document.getElementById('password');var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;ns.call(el,'" + pw + "');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('blur',{bubbles:true}));return'ok';})()")
time.sleep(1.5)
ev("(function(){var el=document.getElementById('password-confirm');if(!el)return'no';var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;ns.call(el,'" + pw + "');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return'ok';})()")
time.sleep(0.5)
print("2) Filled")

# Submit — evaluate click (NO stale ref issues)
r = ev(CLICK_BTN + "('Start using Proton Mail')")
print(f"3) Submit: {r.get('result')}")
time.sleep(8)

snap = get(f"/tabs/{tid}/snapshot?userId=d")["snapshot"]
url = ev("window.location.href").get("result","")
print(f"4) url={url[:70]}, SO={'No, thanks' in snap or 'limited' in snap}")

# Dismiss SO — evaluate click
if "No, thanks" in snap or "limited" in snap:
    r = ev(CLICK_BTN + "('No, thanks')")
    print(f"   SO click: {r.get('result')}")
    time.sleep(5)
    snap = get(f"/tabs/{tid}/snapshot?userId=d")["snapshot"]

print(f"5) HV={'Human Verification' in snap}")

if "Human Verification" in snap:
    # Turnstile
    ts = post(f"/tabs/{tid}/solve-turnstile", {"userId":"d","url":"https://account.proton.me/signup?plan=free&language=en","waitSeconds":10}, timeout=30)
    print(f"   TS: detected={ts.get('turnstileDetected')}, solved={ts.get('solved')}")

    # Click "Use your current email instead"
    r = ev(CLICK_BTN + "('Use your current email')")
    print(f"   UCE: {r.get('result')}")
    time.sleep(3)

    # Hide captcha
    ev("(function(){var c=document.querySelector(\"iframe[title='Captcha']\");if(c){c.style.display='none';}return'ok';})()")

    # Fill email in iframe
    r = evf("(function(){"
        "var inp=document.querySelector('input');if(!inp)return'NI';"
        "inp.removeAttribute('readonly');inp.readOnly=false;"
        "var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
        "ns.call(inp,'" + rec + "');"
        "inp.dispatchEvent(new Event('input',{bubbles:true}));"
        "inp.dispatchEvent(new Event('change',{bubbles:true}));"
        "return'OK:'+inp.value;})()")
    print(f"6) Email: {r.get('result','?')}")
    time.sleep(3)

    # Click "Get verification code"
    r = ev(CLICK_BTN + "('Get verification code')")
    print(f"7) Code btn: {r.get('result')}")
    time.sleep(5)

    # Outlook API
    with open("/home/why/.config/opencode/outlook-accounts.json") as f:
        acc = json.load(f)["luke"]
    d = urllib.parse.urlencode({"client_id":acc["clientId"],"refresh_token":acc["refreshToken"],"grant_type":"refresh_token"}).encode()
    r = urllib.request.Request("https://login.microsoftonline.com/common/oauth2/v2.0/token", data=d, headers={"Content-Type":"application/x-www-form-urlencoded"})
    tk = json.loads(urllib.request.urlopen(r, timeout=15).read())["access_token"]
    q = urllib.parse.quote("$top=5&$orderby=ReceivedDateTime desc&$select=Subject,BodyPreview", safe="&=$")
    r = urllib.request.Request(f"https://outlook.office.com/api/v2.0/me/messages?{q}", headers={"Authorization":"Bearer "+tk})
    known = set()
    for m in json.loads(urllib.request.urlopen(r, timeout=10).read())["value"]:
        if "Proton" in m.get("Subject",""):
            mc = re.search(r"(\d{6})", m.get("BodyPreview",""))
            if mc: known.add(mc.group(1))
    code = None
    for i in range(40):
        time.sleep(3)
        r = urllib.request.Request(f"https://outlook.office.com/api/v2.0/me/messages?{q}", headers={"Authorization":"Bearer "+tk})
        for m in json.loads(urllib.request.urlopen(r, timeout=10).read())["value"]:
            if "Proton" in m.get("Subject",""):
                mc = re.search(r"(\d{6})", m.get("BodyPreview",""))
                if mc and mc.group(1) not in known:
                    code = mc.group(1); break
        if code: break
        if i%10==9: print(f"  [{i}]...")
    if not code: print("❌"); sys.exit(1)
    print(f"8) CODE: {code}")

    # Fill + verify
    ev("(function(){var el=document.getElementById('verification')||document.querySelector('input[type=number]');if(!el)return'NF';var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;ns.call(el,'"+code+"');el.dispatchEvent(new Event('input',{bubbles:true}));return'OK';})()")
    time.sleep(0.5)
    ev(CLICK_BTN + "('Verify')")
    time.sleep(8)
    print("9) Verified")

    for i in range(15):
        time.sleep(3)
        url = ev("window.location.href").get("result","")
        if "mail" in url: print(f"\n✅✅✅ {uname}@proton.me ✅✅✅"); sys.exit(0)
        if "signup" in url: print(f"\n❌ Back"); sys.exit(1)
        print(f"[{i}] {url[:80]}")
else:
    print(f"❌ No HV: {snap[:300]}")
    sys.exit(1)
