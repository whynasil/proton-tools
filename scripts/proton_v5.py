#!/usr/bin/env python3
"""Proton signup v5 - React state inspection + alternative approach."""
import random
from playwright.sync_api import sync_playwright

USER = "faruktest" + str(random.randint(1000, 9999))
PW = "Armada34**"
print(f"User: {USER}")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()
    
    # Monitor network for API calls
    api_calls = []
    def log_request(request):
        if "api" in request.url or "account" in request.url:
            api_calls.append(f"{request.method} {request.url}")
    page.on("request", log_request)
    
    page.goto("https://account.proton.me/mail/signup", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)

    body = page.inner_text("body")
    if "Something went wrong" in body:
        print("CAPTCHA BLOCKED")
        b.close()
        exit()

    # Fill via JS
    page.evaluate(f"""
        (args) => {{
            const [user, pw] = args;
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            const fire = el => {{
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }};
            document.querySelector('#username').focus();
            ns.call(document.querySelector('#username'), user);
            fire(document.querySelector('#username'));
        }}
    """, [USER, PW])
    
    # Use Playwright keyboard to type password (real interaction)
    page.wait_for_timeout(500)
    page.evaluate("window.scrollTo(0, 400)")
    page.wait_for_timeout(300)
    
    # Click password field first
    page.locator("#password").click()
    page.wait_for_timeout(200)
    # Type character by character
    page.locator("#password").fill("")  # clear
    page.keyboard.type(PW, delay=50)
    print("password typed via keyboard")
    
    # Check if confirm appeared
    page.wait_for_timeout(500)
    try:
        page.locator("#password-confirm").click()
        page.wait_for_timeout(100)
        page.locator("#password-confirm").fill("")
        page.keyboard.type(PW, delay=30)
        print("confirm typed via keyboard")
    except:
        print("confirm not interactable, using JS")
        page.evaluate(f"""
            const el = document.querySelector('#password-confirm');
            if (el) {{
                const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                ns.call(el, '{PW}');
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        """)
    
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
    
    # Inspect React state
    react_state = page.evaluate("""
    () => {
        const el = document.querySelector('#username');
        if (!el) return 'NO USERNAME';
        
        const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
        if (!fiberKey) return 'NO FIBER';
        
        let node = el[fiberKey];
        let result = [];
        
        // Walk up to find form component
        for (let i = 0; i < 30 && node; i++) {
            if (node.memoizedState) {
                let state = node.memoizedState;
                let stateInfo = [];
                let j = 0;
                while (state && j < 50) {
                    if (state.queue && state.queue.lastRenderedState !== undefined) {
                        stateInfo.push(`hook${j}=${JSON.stringify(state.queue.lastRenderedState).substring(0, 100)}`);
                    } else if (state.memoizedState !== null && typeof state.memoizedState === 'object') {
                        const keys = Object.keys(state.memoizedState);
                        if (keys.length > 0 && keys.length < 20) {
                            const obj = {};
                            for (const k of keys) {
                                const v = state.memoizedState[k];
                                if (v === true || v === false || typeof v === 'string' || typeof v === 'number') {
                                    obj[k] = v;
                                }
                            }
                            stateInfo.push(`hook${j}=${JSON.stringify(obj).substring(0, 200)}`);
                        }
                    }
                    state = state.next;
                    j++;
                }
                if (stateInfo.length) {
                    result.push(`depth${i} type=${node.type?.name || node.type || '?'}: ${stateInfo.join('; ')}`);
                }
            }
            node = node.return;
        }
        return result.join('\\n') || 'no state found';
    }
    """)
    print(f"\nReact state:\n{react_state}")
    
    # Try page.locator click (Playwright native)
    page.evaluate("window.scrollTo(0, 2000)")
    page.wait_for_timeout(300)
    
    try:
        btn = page.locator("button:has-text('Start using Proton Mail')")
        await_check = btn.count()
        print(f"\nSubmit buttons: {await_check}")
        if await_check > 0:
            # Force click bypassing actionability checks
            btn.first.click(force=True, timeout=5000)
            print("force-clicked submit")
    except Exception as e:
        print(f"force click error: {e}")
    
    page.wait_for_timeout(5000)
    
    url = page.url
    body = page.inner_text("body")
    print(f"\nURL: {url}")
    print(f"Body: {body[:400]}")
    print(f"\nAPI calls: {api_calls}")
    
    if "human verification" in body.lower():
        print("\n✅✅✅ SUCCESS!")
    
    b.close()
