#!/usr/bin/env python3
"""Proton signup v7 - JS focus + keyboard typing + TAB to submit."""
import random
from playwright.sync_api import sync_playwright

USER = "faruktest" + str(random.randint(1000, 9999))
PW = "Armada34**"
print(f"User: {USER}")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()
    
    api_calls = []
    def log(req):
        if "api" in req.url and "telemetry" not in req.url:
            api_calls.append(f"{req.method} {req.url.split('?')[0]}")
    page.on("request", log)
    
    page.goto("https://account.proton.me/mail/signup", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)

    body = page.inner_text("body")
    if "Something went wrong" in body:
        print("CAPTCHA BLOCKED")
        b.close()
        exit()
    
    print("Page loaded, filling form...")
    
    # Scroll to username area
    page.evaluate("document.querySelector('#username').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(500)
    
    # Click + type username via keyboard
    page.locator("#username").click(force=True)
    page.wait_for_timeout(200)
    page.locator("#username").fill("")
    page.keyboard.type(USER, delay=20)
    val = page.input_value("#username")
    print(f"  username: {val}")
    
    page.wait_for_timeout(300)
    
    # Scroll to password
    page.evaluate("document.querySelector('#password').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(500)
    
    # Click + type password
    page.locator("#password").click(force=True)
    page.wait_for_timeout(200)
    page.locator("#password").fill("")
    page.keyboard.type(PW, delay=20)
    print("  password: ***")
    
    page.wait_for_timeout(500)
    
    # Click Free plan
    page.evaluate("""
        const c = document.querySelectorAll('button.card-plan');
        if (c.length) c[0].click();
    """)
    page.wait_for_timeout(500)
    
    # Dismiss SO
    page.evaluate("""
        for (const b of document.querySelectorAll('button')) {
            if (b.textContent.includes('No, thanks')) { b.click(); break; }
        }
    """)
    page.wait_for_timeout(500)
    
    # Type confirm
    page.evaluate("document.querySelector('#password-confirm').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(500)
    
    page.locator("#password-confirm").click(force=True)
    page.wait_for_timeout(200)
    page.locator("#password-confirm").fill("")
    page.keyboard.type(PW, delay=20)
    print("  confirm: ***")
    
    page.wait_for_timeout(500)
    
    # === NEW: Focus submit button and press Enter ===
    page.evaluate("""
        const btn = document.querySelector('button[type="submit"]');
        if (btn) {
            btn.scrollIntoView({block: 'center'});
            btn.focus();
        }
    """)
    page.wait_for_timeout(500)
    
    # Press Enter while submit button is focused
    page.keyboard.press("Enter")
    print("  pressed Enter (submit focused)")
    
    page.wait_for_timeout(6000)
    
    url = page.url
    body = page.inner_text("body")
    print(f"\nURL: {url}")
    print(f"Body: {body[:500]}")
    
    key_calls = [c for c in api_calls if "assets" not in c and "fonts" not in c and "svg" not in c and "png" not in c]
    print(f"\nAPI calls ({len(key_calls)}):")
    for c in key_calls[-10:]:
        print(f"  {c}")
    
    if "human verification" in body.lower():
        print("\n✅✅✅ SUCCESS!")
    elif "email" in body.lower() and "verify" in body.lower():
        print("\n✅ Email verification!")
    else:
        print("\n❌ Failed")
    
    b.close()
