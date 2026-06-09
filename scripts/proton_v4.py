#!/usr/bin/env python3
"""Proton signup v4 - React fiber onClick trigger."""
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

    # Fill via JS
    result = page.evaluate(
        """
        (args) => {
            const [user, pw] = args;
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            const fire = el => {
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            };
            const u = document.querySelector('#username');
            ns.call(u, user); fire(u);
            window.scrollTo(0, 500);
            const p = document.querySelector('#password');
            ns.call(p, pw); fire(p); p.dispatchEvent(new Event('blur', {bubbles: true}));
            const pc = document.querySelector('#password-confirm');
            if (pc) { ns.call(pc, pw); fire(pc); }
            const cards = document.querySelectorAll('button.card-plan');
            if (cards.length) cards[0].click();
            return 'ok';
        }
        """,
        [USER, PW],
    )
    print(f"Fill: {result}")
    page.wait_for_timeout(500)

    # Dismiss SO
    page.evaluate("""
        for (const b of document.querySelectorAll('button')) {
            if (b.textContent.includes('No, thanks')) { b.click(); break; }
        }
    """)
    page.wait_for_timeout(500)

    # Scroll to button
    page.evaluate("window.scrollTo(0, 1500)")
    page.wait_for_timeout(300)

    # === NEW: trigger React onClick via fiber ===
    result = page.evaluate(
        """
        () => {
            const btn = document.querySelector('button[type="submit"]');
            if (!btn) return 'NO SUBMIT BUTTON';

            // Find React fiber key
            const fiberKey = Object.keys(btn).find(k => k.startsWith('__reactFiber'));
            if (!fiberKey) return 'NO REACT FIBER: ' + Object.keys(btn).join(',');

            const fiber = btn[fiberKey];
            if (!fiber) return 'FIBER IS NULL';

            // Walk up to find the memoizedProps with onClick
            let node = fiber;
            let props = null;
            for (let i = 0; i < 20; i++) {
                if (node.memoizedProps && node.memoizedProps.onClick) {
                    props = node.memoizedProps;
                    break;
                }
                node = node.return;
                if (!node) break;
            }

            if (props && props.onClick) {
                // Create a synthetic React event-like object
                const fakeEvent = {
                    preventDefault: () => {},
                    stopPropagation: () => {},
                    target: btn,
                    currentTarget: btn,
                    type: 'click',
                };
                try {
                    props.onClick(fakeEvent);
                    return 'React onClick CALLED successfully';
                } catch (e) {
                    return 'onClick error: ' + e.message;
                }
            }

            // Alternative: try all fiber props
            node = fiber;
            let found = [];
            for (let i = 0; i < 30; i++) {
                if (!node) break;
                if (node.memoizedProps) {
                    const mp = node.memoizedProps;
                    const handlerKeys = Object.keys(mp).filter(k => k.startsWith('on'));
                    if (handlerKeys.length) {
                        found.push(`depth=${i} keys=${handlerKeys.join(',')} type=${node.type}`);
                        // Try onClick or onSubmit
                        const handler = mp.onClick || mp.onSubmit || mp.onPointerDown;
                        if (handler) {
                            handler({preventDefault: () => {}, stopPropagation: () => {}, target: btn});
                            return 'React handler called at depth ' + i;
                        }
                    }
                }
                node = node.return || node.child || node.sibling;
            }
            return 'No handler found: ' + found.join('; ');
        }
        """
    )
    print(f"React trigger: {result}")

    page.wait_for_timeout(5000)

    url = page.url
    body = page.inner_text("body")
    print(f"\nURL: {url}")
    print(f"Body: {body[:400]}")

    if "human verification" in body.lower():
        print("\n✅✅✅ SUCCESS!")
    elif "email" in body.lower() and ("verify" in body.lower() or "recovery" in body.lower()):
        print("\n✅ Email verification!")
    else:
        print("\n❌ Still signup page")

    b.close()
