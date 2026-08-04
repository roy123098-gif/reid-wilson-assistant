import fs from "node:fs";
import path from "node:path";
import type { Pool } from "pg";
import { decryptSecret, encryptSecret } from "./security.js";

export type StoredTransaction = {
  id: string;
  source: "plaid";
  date: string;
  merchant_name?: string;
  name: string;
  amount: number;
  category: string;
  account_id?: string;
  pending?: boolean;
  payment_channel?: string;
  recurring_guess?: boolean;
  needs_review?: boolean;
  plaid_raw_amount?: number;
};

type UserRecord = {
  encryptedAccessToken?: string;
  itemId?: string;
  cursor?: string;
  transactions: StoredTransaction[];
  lastSyncedAt?: string;
};

type SessionRecord = {
  userId: string;
  createdAt: string;
  lastSeenAt: string;
};

type StoreShape = {
  sessions: Record<string, SessionRecord>;
  users: Record<string, UserRecord>;
};

const databaseUrl = process.env.DATABASE_URL?.trim();
const dataFile = path.resolve(process.env.DATA_FILE || "data/dev-storage.json");
let poolPromise: Promise<Pool> | undefined;
let initialized = false;

function localStore(): StoreShape {
  if (!fs.existsSync(dataFile)) return { sessions: {}, users: {} };
  try {
    const parsed = JSON.parse(fs.readFileSync(dataFile, "utf8")) as Partial<StoreShape>;
    return { sessions: parsed.sessions || {}, users: parsed.users || {} };
  } catch {
    return { sessions: {}, users: {} };
  }
}

function writeLocal(store: StoreShape): void {
  fs.mkdirSync(path.dirname(dataFile), { recursive: true });
  fs.writeFileSync(dataFile, JSON.stringify(store, null, 2), { encoding: "utf8", mode: 0o600 });
}

function localUser(store: StoreShape, userId: string): UserRecord {
  store.users[userId] ||= { transactions: [] };
  return store.users[userId];
}

async function db(): Promise<Pool> {
  if (!poolPromise) {
    poolPromise = import("pg").then(({ Pool }) => new Pool({
      connectionString: databaseUrl,
      ssl: process.env.DATABASE_SSL === "true" ? { rejectUnauthorized: false } : undefined,
      max: Number(process.env.DATABASE_POOL_SIZE || 5)
    }));
  }
  return poolPromise;
}

export function storageMode(): "postgres" | "local-development" {
  return databaseUrl ? "postgres" : "local-development";
}

export async function initializeStorage(): Promise<void> {
  if (initialized) return;
  if (databaseUrl) {
    await (await db()).query(`
      CREATE TABLE IF NOT EXISTS app_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL UNIQUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS plaid_items (
        user_id TEXT PRIMARY KEY,
        encrypted_access_token TEXT,
        item_id TEXT,
        cursor TEXT,
        last_synced_at TIMESTAMPTZ
      );
      CREATE TABLE IF NOT EXISTS plaid_transactions (
        user_id TEXT NOT NULL,
        transaction_id TEXT NOT NULL,
        payload JSONB NOT NULL,
        PRIMARY KEY (user_id, transaction_id)
      );
      CREATE INDEX IF NOT EXISTS plaid_transactions_user_date
      ON plaid_transactions (user_id, ((payload->>'date')) DESC);
    `);
  } else if (process.env.NODE_ENV === "production") {
    throw new Error("DATABASE_URL is required in production");
  }
  initialized = true;
}

export async function registerSession(tokenHash: string, userId: string): Promise<void> {
  await initializeStorage();
  if (databaseUrl) {
    await (await db()).query(
      `INSERT INTO app_sessions (token_hash, user_id) VALUES ($1, $2)
       ON CONFLICT (token_hash) DO UPDATE SET last_seen_at = NOW()`,
      [tokenHash, userId]
    );
    return;
  }
  const store = localStore();
  const now = new Date().toISOString();
  store.sessions[tokenHash] = { userId, createdAt: now, lastSeenAt: now };
  writeLocal(store);
}

export async function userForSession(tokenHash: string): Promise<string | null> {
  await initializeStorage();
  if (databaseUrl) {
    const result = await (await db()).query<{ user_id: string }>(
      `UPDATE app_sessions SET last_seen_at = NOW() WHERE token_hash = $1 RETURNING user_id`,
      [tokenHash]
    );
    return result.rows[0]?.user_id || null;
  }
  const store = localStore();
  const record = store.sessions[tokenHash];
  if (!record) return null;
  record.lastSeenAt = new Date().toISOString();
  writeLocal(store);
  return record.userId;
}

export async function saveAccessToken(userId: string, accessToken: string, itemId: string): Promise<void> {
  const encryptedAccessToken = encryptSecret(accessToken);
  if (databaseUrl) {
    await (await db()).query(
      `INSERT INTO plaid_items (user_id, encrypted_access_token, item_id, cursor)
       VALUES ($1, $2, $3, NULL)
       ON CONFLICT (user_id) DO UPDATE SET
         encrypted_access_token = EXCLUDED.encrypted_access_token,
         item_id = EXCLUDED.item_id,
         cursor = NULL,
         last_synced_at = NULL`,
      [userId, encryptedAccessToken, itemId]
    );
    return;
  }
  const store = localStore();
  const record = localUser(store, userId);
  record.encryptedAccessToken = encryptedAccessToken;
  record.itemId = itemId;
  delete record.cursor;
  delete record.lastSyncedAt;
  writeLocal(store);
}

export async function getAccessToken(userId: string): Promise<string | null> {
  if (databaseUrl) {
    const result = await (await db()).query<{ encrypted_access_token: string | null }>(
      `SELECT encrypted_access_token FROM plaid_items WHERE user_id = $1`,
      [userId]
    );
    const encrypted = result.rows[0]?.encrypted_access_token;
    return encrypted ? decryptSecret(encrypted) : null;
  }
  const encrypted = localStore().users[userId]?.encryptedAccessToken;
  return encrypted ? decryptSecret(encrypted) : null;
}

export async function getCursor(userId: string): Promise<string | undefined> {
  if (databaseUrl) {
    const result = await (await db()).query<{ cursor: string | null }>(`SELECT cursor FROM plaid_items WHERE user_id = $1`, [userId]);
    return result.rows[0]?.cursor || undefined;
  }
  return localStore().users[userId]?.cursor;
}

export async function saveSyncState(userId: string, cursor: string, transactions: StoredTransaction[]): Promise<void> {
  const now = new Date().toISOString();
  if (databaseUrl) {
    const client = await (await db()).connect();
    try {
      await client.query("BEGIN");
      await client.query(
        `INSERT INTO plaid_items (user_id, cursor, last_synced_at) VALUES ($1, $2, $3)
         ON CONFLICT (user_id) DO UPDATE SET cursor = EXCLUDED.cursor, last_synced_at = EXCLUDED.last_synced_at`,
        [userId, cursor, now]
      );
      for (const transaction of transactions) {
        await client.query(
          `INSERT INTO plaid_transactions (user_id, transaction_id, payload) VALUES ($1, $2, $3::jsonb)
           ON CONFLICT (user_id, transaction_id) DO UPDATE SET payload = EXCLUDED.payload`,
          [userId, transaction.id, JSON.stringify(transaction)]
        );
      }
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
    return;
  }
  const store = localStore();
  const record = localUser(store, userId);
  const byId = new Map(record.transactions.map((item) => [item.id, item]));
  for (const transaction of transactions) byId.set(transaction.id, transaction);
  record.cursor = cursor;
  record.transactions = Array.from(byId.values()).sort((a, b) => b.date.localeCompare(a.date));
  record.lastSyncedAt = now;
  writeLocal(store);
}

export async function removeTransactions(userId: string, ids: string[]): Promise<void> {
  if (!ids.length) return;
  if (databaseUrl) {
    await (await db()).query(`DELETE FROM plaid_transactions WHERE user_id = $1 AND transaction_id = ANY($2::text[])`, [userId, ids]);
    return;
  }
  const store = localStore();
  const record = localUser(store, userId);
  const removed = new Set(ids);
  record.transactions = record.transactions.filter((item) => !removed.has(item.id));
  writeLocal(store);
}

export async function getTransactions(userId: string): Promise<StoredTransaction[]> {
  if (databaseUrl) {
    const result = await (await db()).query<{ payload: StoredTransaction }>(
      `SELECT payload FROM plaid_transactions WHERE user_id = $1 ORDER BY payload->>'date' DESC`,
      [userId]
    );
    return result.rows.map((row) => row.payload);
  }
  return localStore().users[userId]?.transactions || [];
}

export async function getLastSyncedAt(userId: string): Promise<string | undefined> {
  if (databaseUrl) {
    const result = await (await db()).query<{ last_synced_at: Date | null }>(
      `SELECT last_synced_at FROM plaid_items WHERE user_id = $1`,
      [userId]
    );
    return result.rows[0]?.last_synced_at?.toISOString();
  }
  return localStore().users[userId]?.lastSyncedAt;
}

export async function disconnect(userId: string, deleteSyncedData: boolean): Promise<void> {
  if (databaseUrl) {
    const client = await (await db()).connect();
    try {
      await client.query("BEGIN");
      await client.query(`DELETE FROM plaid_items WHERE user_id = $1`, [userId]);
      if (deleteSyncedData) await client.query(`DELETE FROM plaid_transactions WHERE user_id = $1`, [userId]);
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
    return;
  }
  const store = localStore();
  const record = localUser(store, userId);
  delete record.encryptedAccessToken;
  delete record.itemId;
  delete record.cursor;
  delete record.lastSyncedAt;
  if (deleteSyncedData) record.transactions = [];
  writeLocal(store);
}

export async function deleteUserData(userId: string): Promise<void> {
  if (databaseUrl) {
    const client = await (await db()).connect();
    try {
      await client.query("BEGIN");
      await client.query(`DELETE FROM plaid_transactions WHERE user_id = $1`, [userId]);
      await client.query(`DELETE FROM plaid_items WHERE user_id = $1`, [userId]);
      await client.query(`DELETE FROM app_sessions WHERE user_id = $1`, [userId]);
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
    return;
  }
  const store = localStore();
  delete store.users[userId];
  for (const [tokenHash, session] of Object.entries(store.sessions)) {
    if (session.userId === userId) delete store.sessions[tokenHash];
  }
  writeLocal(store);
}

export async function closeStorage(): Promise<void> {
  if (poolPromise) await (await poolPromise).end();
  poolPromise = undefined;
  initialized = false;
}
