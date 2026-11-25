const encoder = new TextEncoder();

async function hmacSha256(keyBytes, message) {
  const key = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return new Uint8Array(sig);
}

function toHex(bytes) {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqualHex(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

export async function verifyTelegramInitData(initData, botToken, maxAgeSeconds = 86400) {
  if (!initData || !initData.trim()) {
    throw new Error("Missing X-Telegram-Init-Data");
  }
  const params = new URLSearchParams(initData);
  const receivedHash = params.get("hash");
  if (!receivedHash) throw new Error("Missing hash in initData");
  params.delete("hash");

  const authDate = Number(params.get("auth_date"));
  if (!Number.isFinite(authDate) || authDate <= 0) {
    throw new Error("Missing or invalid auth_date");
  }
  const nowSec = Math.floor(Date.now() / 1000);
  if (nowSec - authDate > maxAgeSeconds) {
    throw new Error("Expired initData");
  }

  const pairs = [];
  for (const [k, v] of params.entries()) {
    pairs.push([k, v]);
  }
  pairs.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const dataCheckString = pairs.map(([k, v]) => `${k}=${v}`).join("\n");

  const secretKey = await hmacSha256(encoder.encode("WebAppData"), botToken);
  const expectedHash = toHex(await hmacSha256(secretKey, dataCheckString));
  if (!constantTimeEqualHex(expectedHash, receivedHash.toLowerCase())) {
    throw new Error("Invalid initData signature");
  }

  const userRaw = params.get("user");
  if (!userRaw) throw new Error("Missing user object");
  const userObj = JSON.parse(userRaw);
  if (!Number.isInteger(userObj.id)) throw new Error("Invalid user.id");
  return userObj.id;
}
