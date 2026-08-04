import crypto from "node:crypto";

const ALGORITHM = "aes-256-gcm";

function keyFromEnv(): Buffer {
  const configured = process.env.TOKEN_ENCRYPTION_KEY;
  if (!configured && process.env.NODE_ENV === "production") {
    throw new Error("TOKEN_ENCRYPTION_KEY is required in production");
  }
  const raw = configured || "local-development-only-replace-before-hosting";
  return crypto.createHash("sha256").update(raw).digest();
}

export function encryptSecret(value: string): string {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv(ALGORITHM, keyFromEnv(), iv);
  const encrypted = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  const authTag = cipher.getAuthTag();
  return ["v1", iv.toString("base64"), authTag.toString("base64"), encrypted.toString("base64")].join(".");
}

export function decryptSecret(value: string): string {
  const parts = value.split(".");
  const [ivRaw, authTagRaw, encryptedRaw] = parts[0] === "v1" ? parts.slice(1) : parts;
  if (!ivRaw || !authTagRaw || !encryptedRaw) return "";
  const decipher = crypto.createDecipheriv(ALGORITHM, keyFromEnv(), Buffer.from(ivRaw, "base64"));
  decipher.setAuthTag(Buffer.from(authTagRaw, "base64"));
  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(encryptedRaw, "base64")),
    decipher.final()
  ]);
  return decrypted.toString("utf8");
}

export function hashSessionToken(value: string): string {
  return crypto.createHash("sha256").update(value, "utf8").digest("hex");
}

export function createSessionToken(): string {
  return crypto.randomBytes(32).toString("base64url");
}

export function safeLogEvent(name: string, details: Record<string, unknown> = {}): void {
  const blocked = /secret|token|authorization|password|credential|account|item_id/i;
  const safeDetails = Object.fromEntries(
    Object.entries(details)
      .filter(([key]) => !blocked.test(key))
      .map(([key, value]) => [key, ["string", "number", "boolean"].includes(typeof value) ? value : undefined])
  );
  console.log(JSON.stringify({ event: name, ...safeDetails }));
}
