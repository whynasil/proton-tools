#!/usr/bin/env python3
"""CloakBrowser → Camofox API Bridge Server.

Implements the Camofox REST API using CloakBrowser (stealth Chromium + Playwright).
Drop-in replacement: set CAMOFOX_URL=http://localhost:9377 and Hermes browser
tools work transparently with CloakBrowser.

Start: python server.py [--port 9377]
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

# ═══════════════════════════════════════════════════════════════════════════
# CloakBrowser / Playwright
# ═══════════════════════════════════════════════════════════════════════════

try:
    from cloakbrowser import launch as cloak_launch
    CLOAKBROWSER_AVAILABLE = True
except ImportError:
    CLOAKBROWSER_AVAILABLE = False
    print("WARNING: cloakbrowser not installed. Install: pip install cloakbrowser")

# Fall back to plain Playwright if cloakbrowser not available
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger("cloakbridge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="CloakBridge", version="0.1.0")

# ═══════════════════════════════════════════════════════════════════════════
# Global browser state
# ═══════════════════════════════════════════════════════════════════════════

_browser = None
_playwright = None
_lock = threading.Lock()
# Map: userId → {tabId → {"page": page, "session_key": str}}
_sessions: Dict[str, Dict[str, Any]] = {}

# ═══════════════════════════════════════════════════════════════════════════
# Browser lifecycle
# ═══════════════════════════════════════════════════════════════════════════

def get_browser():
    global _browser, _playwright
    if _browser is not None:
        return _browser

    # Try CloakBrowser first
    if CLOAKBROWSER_AVAILABLE:
        logger.info("Launching CloakBrowser (stealth Chromium)...")
        _browser = cloak_launch(headless=True)
        return _browser

    # Fall back to Playwright
    if PLAYWRIGHT_AVAILABLE:
        logger.info("Launching Playwright (no stealth)...")
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
        return _browser

    raise RuntimeError("Neither CloakBrowser nor Playwright is available")


def get_or_create_session(user_id: str, session_key: str = "") -> Dict[str, Any]:
    """Get or create a session for a user."""
    if user_id not in _sessions:
        _sessions[user_id] = {}

    # Find existing tab with this session_key
    for tab_id, session in _sessions[user_id].items():
        if session.get("session_key") == session_key:
            return {"tab_id": tab_id, "user_id": user_id, "page": session["page"]}

    return {"tab_id": None, "user_id": user_id, "page": None}


# ═══════════════════════════════════════════════════════════════════════════
# Snapshot engine — generate accessibility tree with element refs
# ═══════════════════════════════════════════════════════════════════════════

# Interactive roles that get element refs
INTERACTIVE_ROLES = {
    "link", "button", "textbox", "searchbox", "combobox", "listbox",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option",
    "radio", "checkbox", "switch", "slider", "spinbutton",
    "tab", "treeitem", "listitem", "gridcell", "row",
    "menuitem", "navigation", "separator", "image",
}


def _should_assign_ref(role: str, name: str) -> bool:
    """Determine if an accessibility node should get an element ref."""
    if not role:
        return False
    role_lower = role.lower().replace(" ", "")
    if role_lower in INTERACTIVE_ROLES:
        return True
    # Also assign refs to elements that have meaningful names
    if name and role_lower in ("heading", "article", "region", "main", "navigation"):
        return True
    return False


def generate_snapshot(page) -> Dict[str, Any]:
    """Generate accessibility snapshot with element refs from the current page.
    
    Strategy: inject data-hermes-ref attributes via JS on ALL interactive elements,
    then build a DOM-based text snapshot (more reliable than Playwright's 
    accessibility tree, especially in headless mode).
    """
    # Inject data attributes for click-to-ref mapping + build snapshot
    try:
        result = page.evaluate("""
        (() => {
            // Remove old refs
            document.querySelectorAll('[data-hermes-ref]').forEach(el => {
                el.removeAttribute('data-hermes-ref');
            });

            let refCounter = 1;
            const lines = [];

            // Selectors for interactive elements
            const selectors = [
                'a[href]', 'button', 'input:not([type="hidden"])', 
                'select', 'textarea', 'summary', 'details',
                '[onclick]', '[role="button"]', '[role="link"]',
                '[role="textbox"]', '[role="searchbox"]', '[role="combobox"]',
                '[role="checkbox"]', '[role="radio"]', '[role="switch"]',
                '[role="tab"]', '[role="menuitem"]', '[role="option"]',
                '[role="slider"]', '[role="spinbutton"]', '[tabindex]',
            ];

            const processed = new Set();
            const elements = [];

            for (const sel of selectors) {
                try {
                    const nodes = document.querySelectorAll(sel);
                    for (const node of nodes) {
                        if (processed.has(node)) continue;
                        // Skip hidden/zero-size elements
                        const rect = node.getBoundingClientRect();
                        if (rect.width === 0 && rect.height === 0) continue;
                        processed.add(node);
                        elements.push(node);
                    }
                } catch(e) {}
            }

            // Also collect headings for structure
            for (let h = 1; h <= 6; h++) {
                const headings = document.querySelectorAll('h' + h);
                for (const node of headings) {
                    if (!processed.has(node)) {
                        elements.push(node);
                        processed.add(node);
                    }
                }
            }

            for (const el of elements) {
                const ref = String(refCounter);
                el.setAttribute('data-hermes-ref', ref);
                refCounter++;

                const tag = el.tagName.toLowerCase();
                const role = (el.getAttribute('role') || '').toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                const href = (el.getAttribute('href') || '').substring(0, 120);
                const placeholder = (el.getAttribute('placeholder') || '').substring(0, 60);
                const ariaLabel = (el.getAttribute('aria-label') || '').substring(0, 80);
                const name = (el.getAttribute('name') || '');
                const value = (el.value !== undefined ? String(el.value).substring(0, 40) : '');
                const textContent = (el.textContent || '').trim().substring(0, 80);

                // Derive element type
                let desc = tag;
                if (tag === 'a' || role === 'link') desc = 'link';
                else if (tag === 'button' || role === 'button') desc = 'button';
                else if (tag === 'input' && (type === 'text' || type === 'search' || type === 'email' || type === 'password' || type === 'url' || type === 'tel')) desc = 'textbox';
                else if (tag === 'input' && type === 'checkbox') desc = 'checkbox';
                else if (tag === 'input' && type === 'radio') desc = 'radio';
                else if (tag === 'input' && type === 'submit') desc = 'button';
                else if (tag === 'select' || role === 'combobox' || role === 'listbox') desc = 'combobox';
                else if (tag === 'textarea') desc = 'textbox';
                else if (tag === 'summary') desc = 'button';
                else if (tag.match(/^h[1-6]$/)) desc = 'heading';
                else if (role) desc = role;
                else desc = tag;

                // Build label
                let label = ariaLabel || placeholder || name || textContent || href || '';
                if (value && !label) label = '(value=' + value + ')';

                if (desc === 'heading') {
                    lines.push(`${desc} "${label}" [e${ref}]`);
                } else if (desc === 'textbox') {
                    lines.push(`${desc}${placeholder ? ' placeholder="' + placeholder + '"' : ''} "${label}" [e${ref}]`);
                } else if (desc === 'link') {
                    lines.push(`${desc} "${label}" → ${href || '#'} [e${ref}]`);
                } else {
                    lines.push(`${desc} "${label}" [e${ref}]`);
                }
            }

            window.__hermesRefCount = refCounter - 1;
            return { lines: lines, count: refCounter - 1 };
        })();
        """)
        snapshot_text = "\n".join(result.get("lines", []))
        ref_count = result.get("count", 0)
        
        logger.debug(f"Snapshot generated: {ref_count} refs, {len(snapshot_text)} chars")
        
        return {
            "snapshot": snapshot_text or "[empty page — no interactive elements found]",
            "refsCount": ref_count,
        }
    except Exception as e:
        logger.warning(f"Snapshot generation failed: {e}")
        return {"snapshot": f"[snapshot error: {e}]", "refsCount": 0}


# ═══════════════════════════════════════════════════════════════════════════
# Camofox-compatible API endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    """Health check — Camofox-compatible."""
    return {
        "status": "ok",
        "backend": "cloakbridge",
        "cloakbrowser": CLOAKBROWSER_AVAILABLE,
    }


@app.post("/tabs")
def create_tab(body: Dict[str, Any]):
    """Create a new tab. Body: {userId, sessionKey, url}."""
    user_id = body.get("userId", "default")
    session_key = body.get("sessionKey", "default")
    url = body.get("url", "about:blank")

    try:
        browser = get_browser()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Browser launch failed: {e}")

    with _lock:
        if user_id not in _sessions:
            _sessions[user_id] = {}

        # Create new context + page
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        tab_id = f"tab_{uuid.uuid4().hex[:8]}"
        _sessions[user_id][tab_id] = {
            "page": page,
            "context": context,
            "session_key": session_key,
            "created_at": time.time(),
        }

    # Navigate
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        generate_snapshot(page)  # Pre-inject refs
    except Exception as e:
        logger.warning(f"Navigation to {url} warning: {e}")

    logger.info(f"Created tab {tab_id} for user {user_id} → {url}")
    return {"tabId": tab_id}


@app.get("/tabs")
def list_tabs(userId: str = Query(default="")):
    """List tabs for a user. Query: userId."""
    if userId not in _sessions:
        return {"tabs": []}

    tabs = []
    for tab_id, session in _sessions[userId].items():
        tabs.append({
            "tabId": tab_id,
            "listItemId": session.get("session_key", ""),
        })
    return {"tabs": tabs}


@app.get("/debug/sessions")
def debug_sessions():
    """List ALL sessions across all users (debug)."""
    result = {}
    for uid, tabs in _sessions.items():
        result[uid] = list(tabs.keys())
    return {"user_ids": list(_sessions.keys()), "sessions": result}


@app.post("/tabs/{tab_id}/navigate")
def navigate(tab_id: str, body: Dict[str, Any]):
    """Navigate to URL. Body: {userId, url}."""
    user_id = body.get("userId", "default")
    url = body.get("url", "about:blank")

    page = _get_page(user_id, tab_id)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Pre-inject refs so click/type work immediately
        generate_snapshot(page)
        return {"url": page.url, "title": page.title()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Navigation failed: {e}")


@app.get("/tabs/{tab_id}/snapshot")
def snapshot(tab_id: str, userId: str = Query(default="")):
    """Get accessibility snapshot with element refs."""
    page = _get_page(userId, tab_id)
    result = generate_snapshot(page)
    return result


@app.post("/tabs/{tab_id}/click")
def click(tab_id: str, body: Dict[str, Any]):
    """Click an element by ref or selector. Body: {userId, ref, selector?}.
    Uses Playwright native click for proper React event handling.
    Priority: selector > ref > text match."""
    user_id = body.get("userId", "default")
    ref = body.get("ref", "").lstrip("@e")
    selector = body.get("selector", "")

    page = _get_page(user_id, tab_id)

    def try_click(locator_str, name):
        try:
            loc = page.locator(locator_str)
            if loc.count():
                loc.first.scroll_into_view_if_needed()
                loc.first.click(force=False, timeout=5000)
                return {"url": page.url, "ok": True, "method": name}
        except:
            pass
        return None

    # 1. Try explicit CSS selector
    if selector:
        result = try_click(selector, "selector")
        if result:
            return result

    # 2. Try data-hermes-ref
    if ref:
        result = try_click(f"[data-hermes-ref='{ref}']", "ref")
        if result:
            return result
        # Also try ref as selector (e.g. "#username")
        result = try_click(ref if ref.startswith("#") or ref.startswith(".") else f"#{ref}", "ref-as-id")
        if result:
            return result

    # 3. Try text match from selector
    if selector:
        try:
            loc = page.get_by_text(selector, exact=False)
            if loc.count():
                loc.first.click(force=True)
                return {"url": page.url, "ok": True, "method": "text"}
        except:
            pass

    # 4. Last resort: JS click with broad search - use page.evaluateHandle for safety
    try:
        search = selector or ref or ""
        # Build safe JS without embedding user strings in code
        result = page.evaluate("""
            (search) => {
                let el = null;
                if (search.startsWith('#')) el = document.querySelector(search);
                else if (search.startsWith('.')) el = document.querySelector(search);
                else if (search) {
                    const btns = document.querySelectorAll('button');
                    for (let i = 0; i < btns.length; i++) {
                        if (btns[i].textContent.includes(search)) {
                            el = btns[i];
                            break;
                        }
                    }
                }
                if (!el) return JSON.stringify({ok: false, error: 'not found'});
                el.scrollIntoView({block: 'center'});
                el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                return JSON.stringify({ok: true, tag: el.tagName});
            }
        """, search)
        data = json.loads(result)
        return {"url": page.url, "ok": data.get("ok", False), "fallback": "js"}
    except Exception as e:
        return {"error": str(e)[:200], "url": page.url}


@app.post("/tabs/{tab_id}/type")
def type_text(tab_id: str, body: Dict[str, Any]):
    """Type text into element via JS native setter. Body: {userId, ref?, selector?, text}.
    Uses native JS value setter + events — reliable, never blocks."""
    user_id = body.get("userId", "default")
    ref = body.get("ref", "").lstrip("@e")
    selector = body.get("selector", "")
    text = body.get("text", "")

    page = _get_page(user_id, tab_id)

    # Build search: prefer selector, then ref-as-id
    if selector:
        search = selector
    elif ref and not ref.startswith(("#", ".")):
        search = f"#{ref}"
    else:
        search = ref or ""

    try:
        result = page.evaluate("""
            (args) => {
                const search = args[0];
                const text = args[1];
                const el = document.querySelector(search);
                if (!el) return JSON.stringify({ok: false, error: 'not found: ' + search});
                const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                ns.call(el, text);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return JSON.stringify({ok: true, value: el.value.length > 0 ? '***' : 'empty', search: search});
            }
        """, [search, text])
        data = json.loads(result)
        return {"ok": data.get("ok", False), "url": page.url, "method": "js", **{k: v for k, v in data.items() if k != "ok"}}
    except Exception as e:
        return {"error": str(e)[:200], "url": page.url}


@app.post("/tabs/{tab_id}/evaluate")
def evaluate_js(tab_id: str, body: Dict[str, Any]):
    """Evaluate JavaScript in the page. Body: {userId, expression}.
    NEVER returns 500 — wraps JS errors in result object."""
    user_id = body.get("userId", "default")
    expression = body.get("expression", "")
    page = _get_page(user_id, tab_id)
    try:
        result = page.evaluate(expression)
        return {"result": result}
    except Exception as e:
        # Wrap JS errors instead of 500
        return {"result": None, "error": str(e)[:200]}


@app.post("/tabs/{tab_id}/evaluate-in-frame") 
def evaluate_js_in_frame(tab_id: str, body: Dict[str, Any]):
    """Evaluate JavaScript in an iframe. Body: {userId, expression, frameUrlPrefix?}."""
    user_id = body.get("userId", "default")
    expression = body.get("expression", "")
    prefix = body.get("frameUrlPrefix", "")

    page = _get_page(user_id, tab_id)
    try:
        # Find matching frame
        for frame in page.frames:
            if prefix and prefix not in frame.url:
                continue
            if not prefix and frame == page.main_frame:
                continue
            # Skip hidden frames
            if frame.url == "about:blank":
                continue
            try:
                result = frame.evaluate(expression)
                return {"result": result, "frameUrl": frame.url}
            except Exception:
                continue
        raise Exception("No matching frame found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Frame evaluate failed: {e}")

@app.post("/tabs/{tab_id}/type-in-frame")
def type_in_frame(tab_id: str, body: Dict[str, Any]):
    """Type text into an input inside an iframe. Body: {userId, text, frameUrlPrefix?}.
    Uses Playwright keyboard.type() for proper React event handling."""
    user_id = body.get("userId", "default")
    text = body.get("text", "")
    prefix = body.get("frameUrlPrefix", "")

    page = _get_page(user_id, tab_id)
    try:
        for frame in page.frames:
            if prefix and prefix not in frame.url:
                continue
            if not prefix and frame == page.main_frame:
                continue
            if frame.url == "about:blank":
                continue
            try:
                inp = frame.locator("input").first
                if inp.count():
                    inp.click()
                    inp.fill("")
                    inp.type(text, delay=50)
                    return {"ok": True, "frameUrl": frame.url, "value": inp.input_value()}
            except Exception:
                continue
        return {"error": "No input found in frame"}
    except Exception as e:
        return {"error": str(e)[:200]}


@app.post("/tabs/{tab_id}/scroll")
def scroll(tab_id: str, body: Dict[str, Any]):
    """Scroll the page. Body: {userId, direction}."""
    user_id = body.get("userId", "default")
    direction = body.get("direction", "down")

    page = _get_page(user_id, tab_id)
    try:
        if direction == "down":
            page.evaluate("window.scrollBy(0, window.innerHeight)")
        elif direction == "up":
            page.evaluate("window.scrollBy(0, -window.innerHeight)")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scroll failed: {e}")


@app.post("/tabs/{tab_id}/back")
def back(tab_id: str, body: Dict[str, Any]):
    """Navigate back."""
    user_id = body.get("userId", "default")
    page = _get_page(user_id, tab_id)

    try:
        page.go_back(timeout=10000)
        return {"url": page.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Back failed: {e}")


@app.post("/tabs/{tab_id}/press")
def press_key(tab_id: str, body: Dict[str, Any]):
    """Press a keyboard key. Body: {userId, key}."""
    user_id = body.get("userId", "default")
    key = body.get("key", "")

    page = _get_page(user_id, tab_id)
    try:
        page.keyboard.press(key)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Press failed: {e}")


@app.get("/tabs/{tab_id}/screenshot")
def screenshot(tab_id: str, userId: str = Query(default="")):
    """Take a screenshot. Returns PNG binary."""
    page = _get_page(userId, tab_id)
    try:
        png_bytes = page.screenshot(type="png", full_page=False)
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {e}")


@app.get("/tabs/{tab_id}/cookies")
def get_cookies(tab_id: str, userId: str = Query(default="")):
    """Get all cookies for a tab's page."""
    page = _get_page(userId, tab_id)
    try:
        cookies = page.context.cookies()
        return {"cookies": cookies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cookies: {e}")


@app.post("/tabs/{tab_id}/cookies")
def set_cookies(tab_id: str, body: Dict[str, Any]):
    """Set cookies for a tab's browser context. Body: {userId, cookies: [{name, value, domain, ...}]}."""
    user_id = body.get("userId", "default")
    cookies = body.get("cookies", [])
    page = _get_page(user_id, tab_id)
    try:
        page.context.add_cookies(cookies)
        return {"ok": True, "count": len(cookies)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set cookies: {e}")


@app.post("/tabs/{tab_id}/solve-turnstile")
def solve_turnstile(tab_id: str, body: Dict[str, Any]):
    """Navigate to a URL with cookies, detect Turnstile, click it, return cf_clearance.
    Body: {userId, url?, cookies?: [...], waitSeconds?: 15}"""
    user_id = body.get("userId", "default")
    url = body.get("url", "https://app.notion.com")
    cookies_list = body.get("cookies", [])
    wait_seconds = body.get("waitSeconds", 15)

    page = _get_page(user_id, tab_id)

    try:
        # Set cookies if provided
        if cookies_list:
            page.context.add_cookies(cookies_list)

        # Navigate
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        import time as _time

        # Detect Cloudflare Turnstile
        has_challenge = page.evaluate("""
            () => {
                return document.body.innerHTML.includes('challenge-platform') ||
                       !!document.querySelector('iframe[src*="challenges.cloudflare.com"]') ||
                       !!document.querySelector('input[name="cf-turnstile-response"]');
            }
        """)

        result = {"turnstileDetected": has_challenge, "url": page.url}

        if has_challenge:
            logger.info(f"Turnstile detected on {url}, attempting click...")

            # Repeatedly try to click the Turnstile checkbox
            clicked = False
            for attempt in range(20):
                if attempt > 0:
                    _time.sleep(1)

                # Check if we already have cf_clearance
                cookies = page.context.cookies()
                if any(c.get("name") == "cf_clearance" for c in cookies):
                    logger.info(f"cf_clearance obtained after {attempt} attempts")
                    result["cfClearance"] = next(
                        c["value"] for c in cookies if c.get("name") == "cf_clearance"
                    )
                    result["solved"] = True
                    break

                # Try to find and click the Turnstile element
                try:
                    bounding = page.evaluate("""
                        () => {
                            const el = document.querySelector('div:has(> div > div > input[name="cf-turnstile-response"])');
                            if (!el) return null;
                            const r = el.getBoundingClientRect();
                            if (r.width <= 250 || r.height <= 40) return null;
                            return {x: r.x, y: r.y, width: r.width, height: r.height};
                        }
                    """)
                    if bounding:
                        x = bounding["x"] + 25
                        y = bounding["y"] + 35
                        page.mouse.click(x, y)
                        clicked = True
                        _time.sleep(2)
                except Exception:
                    pass

            # Final check
            cookies = page.context.cookies()
            if not result.get("solved"):
                cf = next((c["value"] for c in cookies if c.get("name") == "cf_clearance"), None)
                if cf:
                    result["cfClearance"] = cf
                    result["solved"] = True
                else:
                    result["solved"] = False
                    result["clicked"] = clicked

            result["cookies"] = [
                {"name": c["name"], "value": c["value"], "domain": c.get("domain", "")}
                for c in cookies
            ]
        else:
            logger.info(f"No Turnstile on {url}")
            result["solved"] = False

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Turnstile solve failed: {e}")


@app.delete("/sessions/{user_id}")
def close_session(user_id: str):
    """Close all tabs for a user."""
    with _lock:
        if user_id in _sessions:
            for tab_id, session in list(_sessions[user_id].items()):
                try:
                    session["page"].close()
                    session["context"].close()
                except Exception as e:
                    logger.warning(f"Error closing tab {tab_id}: {e}")
            del _sessions[user_id]
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_page(user_id: str, tab_id: str):
    """Get page for a user/tab, raising 404 if not found."""
    user_sessions = _sessions.get(user_id, {})
    session = user_sessions.get(tab_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Tab {tab_id} not found")
    return session["page"]


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="CloakBridge — Camofox API via CloakBrowser")
    parser.add_argument("--port", type=int, default=9377, help="HTTP port (default: 9377)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind host")
    args = parser.parse_args()

    logger.info(f"Starting CloakBridge on {args.host}:{args.port}")
    logger.info(f"CloakBrowser available: {CLOAKBROWSER_AVAILABLE}")
    logger.info(f"Playwright fallback: {PLAYWRIGHT_AVAILABLE}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
