#!/usr/bin/env python3
"""Proton signup v8 - JS focus/dispatch + page.keyboard.type."""
import random
from playwright.sync_api import sync_playwright

USER = "faruktest" + str(random.randint(1000, 9999))
PW = "Armada34**"
print(f"User: {USER}")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()
    
    page.goto("https://account.proton.me/mail/signup", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)

    body = page.inner_text("body")
    if "Something went wrong" in body:
        print("CAPTCHA BLOCKED")
        b.close()
        exit()
    
    # Use JS to focus each field, then page.keyboard to type
    def type_into(selector, text):
        """Focus element via JS, then type via Playwright keyboard."""
        page.evaluate(f"""
            const el = document.querySelector('{selector}');
            if (el) {{
                el.scrollIntoView({{block: 'center'}});
                el.focus();
                el.dispatchEvent(new FocusEvent('focus', {{bubbles: true}}));
            }}
        """)
        page.wait_for_timeout(300)
        page.keyboard.press("Control+a")  # select all
        page.keyboard.press("Delete")    # clear
        page.keyboard.type(text, delay=15)
    
    print("Filling form...")
    
    type_into("#username", USER)
    val = page.evaluate("document.querySelector('#username').value")
    print(f"  username: {val}")
    
    type_into("#password", PW)
    print("  password: ***")
    
    # Click Free plan
    page.evaluate("document.querySelectorAll('button.card-plan')[0]?.click()")
    page.wait_for_timeout(500)
    
    # Dismiss SO
    page.evaluate("""
        for (const b of document.querySelectorAll('button')) {
            if (b.textContent.includes('No, thanks')) { b.click(); break; }
        }
    """)
    page.wait_for_timeout(500)
    
    type_into("#password-confirm", PW)
    print("  confirm: ***")
    
    # Focus submit + TAB to submit button + Enter
    page.evaluate("""
        const el = document.querySelector('#password-confirm');
        if (el) el.dispatchEvent(new Event('blur', {bubbles: true}));
    """)
    page.wait_for_timeout(500)
    
    # Press TAB to move to submit button, then Enter
    page.keyboard.press("Tab")
    page.wait_for_timeout(200)
    page.keyboard.press("Tab")
    page.wait_for_timeout(200)
    page.keyboard.press("Tab")
    page.wait_for_timeout(200)
    page.keyboard.press("Tab")
    page.wait_for_timeout(200)
    page.keyboard.press("Tab")
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")
    print("  TABx5 + Enter")
    
    page.wait_for_timeout(6000)
    
    url = page.url
    body = page.inner_text("body")
    print(f"\nURL: {url}")
    print(f"Body: {body[:500]}")
    
    if "human verification" in body.lower():
        print("\n✅✅✅ SUCCESS!")
    elif "email" in body.lower() and "verify" in body.lower():
        print("\n✅ Email verification!")
    else:
        print("\n❌ Failed")
    
    b.close()
