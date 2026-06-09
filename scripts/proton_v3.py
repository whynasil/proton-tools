#!/usr/bin/env python3
"""Proton signup via Playwright - force fill + submit."""
import json, random
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

    # ALL filling via JS evaluate
    result = page.evaluate(
        """
        (args) => {
            const user = args[0];
            const pw = args[1];
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            const fire = el => {
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            };

            const u = document.querySelector('#username');
            if (!u) return 'NO USERNAME';
            ns.call(u, user);
            fire(u);

            // Scroll to reveal password fields
            window.scrollTo(0, 500);

            const p = document.querySelector('#password');
            if (p) {
                ns.call(p, pw);
                fire(p);
                p.dispatchEvent(new Event('blur', {bubbles: true}));
            }

            const pc = document.querySelector('#password-confirm');
            if (pc) {
                ns.call(pc, pw);
                fire(pc);
            }

            // Click Free plan (first card)
            const cards = document.querySelectorAll('button.card-plan');
            if (cards.length) cards[0].click();

            return 'filled: u=' + u.value + ' pw=' + (p ? !!p.value : false) + ' pwc=' + (pc ? !!pc.value : false);
        }
        """,
        [USER, PW],
    )
    print(f"Fill: {result}")

    page.wait_for_timeout(500)

    # Dismiss Special Offer
    page.evaluate(
        """
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            if (b.textContent.includes('No, thanks')) { b.click(); break; }
        }
        """
    )
    print("SO checked")

    page.wait_for_timeout(500)

    # Scroll to button
    page.evaluate("window.scrollTo(0, 1500)")
    page.wait_for_timeout(300)

    # Click submit
    result = page.evaluate(
        """
        () => {
            const btns = document.querySelectorAll('button');
            let found = 'NOT FOUND';
            for (const b of btns) {
                if (b.textContent.includes('Start using Proton Mail')) {
                    b.scrollIntoView({block: 'center'});
                    b.click();
                    found = 'clicked: ' + b.textContent.trim();
                    break;
                }
            }
            return found;
        }
        """
    )
    print(f"Click submit: {result}")

    page.wait_for_timeout(6000)

    url = page.url
    body = page.inner_text("body")
    print(f"\nURL: {url}")
    print(f"Body: {body[:500]}")

    if "human verification" in body.lower() or "challenge" in body.lower():
        print("\n✅✅✅ SUCCESS — HV page!")
    elif "email" in body.lower() and ("verify" in body.lower() or "code" in body.lower()):
        print("\n✅ Email verification page!")
    else:
        print("\n❌ Still on signup page")

    b.close()
