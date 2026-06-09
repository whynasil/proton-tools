#!/usr/bin/env python3
"""Proton signup - handle Human Verification dialog."""
import subprocess, json, time

CB = "http://localhost:9377"
USER = "default"
tid = "tab_24f156da"

def cb(method, path, body=None):
    cmd = ["curl", "-s", "--max-time", "30", f"{CB}{path}", "-X", method]
    if body:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
    try:
        return json.loads(r.stdout) if r.stdout.strip() else None
    except:
        return r.stdout.strip()

# Step 1: Get current page values
print("Getting current field values...", flush=True)
js_get = """
(() => {
  const inputs = document.querySelectorAll('input');
  const result = {};
  inputs.forEach(inp => {
    result[inp.id || inp.placeholder || inp.name || 'anon'] = {
      value: inp.value,
      type: inp.type,
      placeholder: inp.placeholder || ''
    };
  });
  return JSON.stringify(result);
})()
"""
res = cb("POST", f"/tabs/{tid}/evaluate", {"userId": USER, "expression": js_get})
print(f"Fields: {res}", flush=True)

# Step 2: Read the auto-generated password and fill confirm
print("\nSyncing passwords...", flush=True)
js_sync = """
(() => {
  const allInputs = document.querySelectorAll('input');
  let pw = '';
  let confirmInput = null;
  
  allInputs.forEach(inp => {
    if (inp.id === 'password' || inp.name === 'password') {
      pw = inp.value;
    }
    if (inp.id === 'password-confirm' || inp.placeholder?.toLowerCase().includes('confirm')) {
      confirmInput = inp;
    }
  });
  
  if (!pw) {
    // Try any password-adjacent field
    allInputs.forEach(inp => {
      if (!pw && inp.value.length > 5) pw = inp.value;
    });
  }
  
  if (confirmInput && pw) {
    const ns = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    ns.call(confirmInput, pw);
    confirmInput.dispatchEvent(new Event('input', { bubbles: true }));
    confirmInput.dispatchEvent(new Event('change', { bubbles: true }));
    return JSON.stringify({synced: true, pw_len: pw.length});
  }
  return JSON.stringify({synced: false, pw_found: !!pw, confirm_found: !!confirmInput});
})()
"""
res = cb("POST", f"/tabs/{tid}/evaluate", {"userId": USER, "expression": js_sync})
print(f"Sync: {res}", flush=True)

time.sleep(2)

# Step 3: Fill the verification email textbox
print("\nFilling verification email...", flush=True)
js_email = """
(() => {
  // Find the email input in the human verification dialog
  const inputs = document.querySelectorAll('input[type="email"], input#email');
  const email = 'miamartin9379@mailim.eu.cc';
  
  if (inputs.length > 0) {
    const el = inputs[0];
    const ns = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    ns.call(el, email);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return JSON.stringify({filled: true, id: el.id, email: email});
  }
  
  // Try textbox e18
  const allInputs = document.querySelectorAll('input:not([type="hidden"])');
  for (const inp of allInputs) {
    if (!inp.value && inp.type !== 'password') {
      const ns = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
      ).set;
      ns.call(inp, email);
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      return JSON.stringify({filled: true, id: inp.id, type: inp.type});
    }
  }
  return JSON.stringify({error: 'no empty input', inputs: allInputs.length});
})()
"""
res = cb("POST", f"/tabs/{tid}/evaluate", {"userId": USER, "expression": js_email})
print(f"Email fill: {res}", flush=True)

time.sleep(2)

# Step 4: Click "Get verification code"
print("\nClicking Get verification code...", flush=True)
js_click = """
(() => {
  const btns = document.querySelectorAll('button');
  for (const b of btns) {
    if (b.textContent.includes('verification') || b.textContent.includes('Get')) {
      b.click();
      return 'clicked: ' + b.textContent.trim().substring(0,40);
    }
  }
  // Try by ref 14
  const el = document.querySelector('[data-hermes-ref="14"]');
  if (el) { el.click(); return 'clicked ref14'; }
  return 'not found';
})()
"""
res = cb("POST", f"/tabs/{tid}/evaluate", {"userId": USER, "expression": js_click})
print(f"Click: {res}", flush=True)

time.sleep(6)

# Step 5: Snapshot
snap = cb("GET", f"/tabs/{tid}/snapshot?userId={USER}")
if snap:
    print(f"\nResult: {snap.get('snapshot', '')[:3000]}", flush=True)

# Screenshot
subprocess.run(["curl", "-s", f"{CB}/tabs/{tid}/screenshot?userId={USER}",
    "-o", "/home/test/proton_verify.png"], timeout=15)
sz = subprocess.run(["stat", "-c%s", "/home/test/proton_verify.png"],
    capture_output=True, text=True)
print(f"Screenshot: {sz.stdout.strip()} bytes", flush=True)
