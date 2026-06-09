#!/usr/bin/env node
import { readFileSync, writeFileSync } from "fs";

const ACCOUNTS_PATH = `${process.env.HOME}/.config/opencode/outlook-accounts.json`;
const DEFAULT_CLIENT = "9e5f94bc-e8a4-4e73-b8be-63364c29d753";

// ── account storage ──────────────────────────────────────────────────
function loadAccounts() {
  try {
    return JSON.parse(readFileSync(ACCOUNTS_PATH, "utf8"));
  } catch {
    return {};
  }
}
function saveAccounts(acc) {
  writeFileSync(ACCOUNTS_PATH, JSON.stringify(acc, null, 2), "utf8");
}

// ── token ────────────────────────────────────────────────────────────
async function getAccessToken(refreshToken, clientId) {
  const params = new URLSearchParams({
    client_id: clientId,
    grant_type: "refresh_token",
    refresh_token: refreshToken,
  });
  const res = await fetch(
    "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: params.toString() }
  );
  const data = await res.json();
  if (data.error) throw new Error(`Token error: ${JSON.stringify(data)}`);
  return data.access_token;
}

async function api(path, token) {
  const res = await fetch(`https://outlook.office.com/api/v2.0${path}`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err.slice(0, 300)}`);
  }
  return res.json();
}

// ── actions ──────────────────────────────────────────────────────────
async function listInbox(token, limit) {
  const data = await api(
    `/me/messages?$top=${limit}&$orderby=ReceivedDateTime desc&$select=Id,Subject,From,ReceivedDateTime,BodyPreview,IsRead`,
    token
  );
  const messages = data.value || [];
  for (const m of messages) {
    const icon = m.IsRead ? "✓" : "●";
    const from = m.From?.EmailAddress?.Name || m.From?.EmailAddress?.Address || "?";
    const date = (m.ReceivedDateTime || "").slice(0, 16).replace("T", " ");
    const subj = m.Subject || "(konu yok)";
    const preview = (m.BodyPreview || "").replace(/\s+/g, " ").slice(0, 100);
    console.log(`[${icon}] ${date} | ${from}`);
    console.log(`   ${subj}`);
    console.log(`   ${preview}`);
    console.log(`   ID: ${m.Id}`);
    console.log();
  }
  console.log(`${messages.length} mesaj`);
}

async function readMessage(token, id) {
  const m = await api(`/me/messages/${id}`, token);
  console.log(`Kimden : ${m.From?.EmailAddress?.Name} <${m.From?.EmailAddress?.Address}>`);
  console.log(`Konu   : ${m.Subject}`);
  console.log(`Tarih  : ${(m.ReceivedDateTime || "").replace("T", " ").replace("Z", "")}`);
  console.log(`Okundu : ${m.IsRead ? "Evet" : "Hayır"}`);
  console.log(`---`);
  const content = m.Body?.Content || "";
  const text = content
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  console.log(text);
  console.log(`---`);
  if (m.HasAttachments && m.Attachments?.length) {
    for (const a of m.Attachments) {
      console.log(`[Eklenti] ${a.Name} (${a.ContentType || "?"} ${a.Size ? Math.round(a.Size/1024)+"KB" : ""})`);
    }
  }
  if (m.ToRecipients?.length) {
    console.log(`Alıcı   : ${m.ToRecipients.map(r => r.EmailAddress.Address).join(", ")}`);
  }
  if (m.CcRecipients?.length) {
    console.log(`CC     : ${m.CcRecipients.map(r => r.EmailAddress.Address).join(", ")}`);
  }
}

async function listFolders(token) {
  const data = await api("/me/MailFolders?$top=20&$select=Id,DisplayName,TotalItemCount,UnreadItemCount", token);
  for (const f of data.value || []) {
    const name = f.DisplayName.padEnd(26);
    const unread = String(f.UnreadItemCount).padStart(3);
    const total = String(f.TotalItemCount).padStart(4);
    console.log(`${name} ${unread} okunmamış / ${total} toplam`);
  }
}

// ── main ─────────────────────────────────────────────────────────────
const args = process.argv.slice(2);

// parse --account
let accountId = "luke";
const accountIdx = args.indexOf("--account");
if (accountIdx !== -1 && accountIdx + 1 < args.length) {
  accountId = args[accountIdx + 1];
  args.splice(accountIdx, 2);
}
const action = args[0] || "list";
const param = args[1] || "10";

try {
  // ── account management (no auth needed) ──
  if (action === "accounts") {
    const sub = param;
    const accounts = loadAccounts();

    if (sub === "list") {
      if (Object.keys(accounts).length === 0) {
        console.log("Henüz kayıtlı hesap yok.");
      } else {
        for (const [id, a] of Object.entries(accounts)) {
          console.log(`[${id}] ${a.label || id}: ${a.user} (client: ${a.clientId || DEFAULT_CLIENT})`);
        }
      }
      process.exit(0);
    }

    if (sub === "add") {
      const id = args[2] || "default";
      const user = args[3];
      const refreshToken = args[4];
      const clientId = args[5] || DEFAULT_CLIENT;
      const label = args[6] || id;

      if (!user || !refreshToken) {
        console.error("Kullanım: node outlook-mail.mjs accounts add <id> <email> <refreshToken> [clientId] [label]");
        process.exit(1);
      }

      const acc = loadAccounts();
      acc[id] = { user, refreshToken, clientId, label };
      saveAccounts(acc);
      console.log(`✅ Hesap eklendi: [${id}] ${label} <${user}>`);
      process.exit(0);
    }

    if (sub === "add-raw") {
      const id = args[2] || "default";
      const raw = args[3];
      const label = args[4] || id;

      if (!raw) {
        console.error("Kullanım: node outlook-mail.mjs accounts add-raw <id> \"email|pass|refreshToken|clientId\" [label]");
        process.exit(1);
      }

      const parts = raw.split("|");
      if (parts.length < 3) {
        console.error("Hatalı format. Beklenen: email|password|refreshToken|clientId");
        process.exit(1);
      }

      const user = parts[0];
      const password = parts[1] || "";
      const refreshToken = parts[2];
      const clientId = parts[3] || DEFAULT_CLIENT;

      const acc = loadAccounts();
      acc[id] = { user, refreshToken, clientId, label, password, raw };
      saveAccounts(acc);
      console.log(`✅ Hesap eklendi: [${id}] ${label} <${user}> (raw format saklandı)`);
      process.exit(0);
    }

    if (sub === "remove") {
      const id = args[2];
      if (!id) {
        console.error("Kullanım: node outlook-mail.mjs accounts remove <id>");
        process.exit(1);
      }
      const acc = loadAccounts();
      if (!acc[id]) {
        console.error(`Hesap [${id}] bulunamadı.`);
        process.exit(1);
      }
      delete acc[id];
      saveAccounts(acc);
      console.log(`🗑️  Hesap silindi: [${id}]`);
      process.exit(0);
    }

    console.error(`Bilinmeyen alt komut: ${sub}`);
    process.exit(1);
  }

  // ── mail operations ──
  const accounts = loadAccounts();
  const account = accounts[accountId];
  if (!account) {
    console.error(`Hesap [${accountId}] bulunamadı. Kayıtlı hesaplar:`);
    for (const [id, a] of Object.entries(accounts)) {
      console.error(`  [${id}] ${a.label || id}`);
    }
    process.exit(1);
  }

  console.error(`[${accountId}] ${account.label || account.user}`);
  const token = await getAccessToken(account.refreshToken, account.clientId);

  switch (action) {
    case "list":
      await listInbox(token, Math.min(parseInt(param) || 10, 50));
      break;
    case "read":
      if (!param || param === "10") {
        console.error("Kullanım: node outlook-mail.mjs read <message-id>");
        process.exit(1);
      }
      await readMessage(token, param);
      break;
    case "folders":
      await listFolders(token);
      break;
    default:
      console.error("Kullanım: node outlook-mail.mjs [--account <id>] [list|read|folders|accounts]");
      process.exit(1);
  }
} catch (e) {
  console.error(`Hata: ${e.message}`);
  process.exit(1);
}
