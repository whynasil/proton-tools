#!/usr/bin/env python3
"""Proton signup v6 - ALL keyboard typing, no JS setters."""
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
        if "api" in req.url and not "telemetry" in req.url and not "assets" in req.url:
            api_calls.append(f"{req.method} {req.url}")
    page.on("request", log)
    
    page.goto("https://account.proton.me/mail/signup", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)

    body = page.inner_text("body")
    if "Something went wrong" in body:
        print("CAPTCHA BLOCKED")
        b.close()
        exit()
    
    print("Page loaded")
    
    # === STEP 1: Type username via keyboard ===
    # First click on username to focus
    page.locator("#username").click(force=True)
    page.wait_for_timeout(200)
    page.locator("#username").fill("")  # clear
    page.keyboard.type(USER, delay=30)
    print(f"  typed username: {page.input_value('#username')}")
    page.wait_for_timeout(300)
    
    # === STEP 2: Scroll to password and type ===
    page.evaluate("window.scrollTo(0, 500)")
    page.wait_for_timeout(300)
    
    page.locator("#password").click(force=True)
    page.wait_for_timeout(200)
    page.locator("#password").fill("")
    page.keyboard.type(PW, delay=30)
    print("  typed password")
    page.wait_for_timeout(300)
    
    # === STEP 3: Click Free plan ===
    page.evaluate("document.querySelectorAll('button.card-plan')[0]?.click()")
    page.wait_for_timeout(500)
    
    # === STEP 4: Dismiss Special Offer ===
    page.evaluate("""
        for (const b of document.querySelectorAll('button')) {
            if (b.textContent.includes('No, thanks')) { b.click(); break; }
        }
    """)
    page.wait_for_timeout(300)
    
    # === STEP 5: Type password confirm ===
    page.locator("#password-confirm").click(force=True)
    page.wait_for_timeout(200)
    page.locator("#password-confirm").fill("")
    page.keyboard.type(PW, delay=30)
    print("  typed confirm")
    page.wait_for_timeout(300)
    
    # === STEP 6: Scroll to submit button and press Enter ===
    page.evaluate("window.scrollTo(0, 2000)")
    page.wait_for_timeout(500)
    
    # Click submit to focus, then press Enter
    btn = page.locator("button:has-text('Start using Proton Mail')")
    btn.click(force=True)
    page.wait_for_timeout(500)
    page.keyboard.press("Enter")
    print("  pressed Enter on submit btn")
    
    page.wait_for_timeout(6000)
    
    url = page.url
    body = page.inner_text("body")
    print(f"\nURL: {url}")
    print(f"Body: {body[:500]}")
    print(f"\nKey API calls:")
    for c in api_calls:
        if "telemetry" not in c and "assets" not in c and "fonts" not in c:
            print(f"  {c}")
    
    if "human verification" in body.lower() or "challenge" in body.lower():
        print("\n✅✅✅ SUCCESS — HV page!")
    elif "verify" in body.lower() and ("email" in body.lower() or "code" in body.lower()):
        print("\n✅ Email verification!")
    else:
        print("\n❌ Form submit failed")
        # Check chargebee/errors
        errors = page.evaluate("""
        Array.from(document.querySelectorAll('[class*=\"error\"], [class*=\"danger\"], [role=\"alert\"]'))
            .map(e => e.textContent.trim()).filter(t => t)
        """)
        if errors:
            print(f"Page errors: {errors}")
    
    b.close()
