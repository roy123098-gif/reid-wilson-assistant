import express from "express";
import { RemovedTransaction } from "plaid";
import { hasPlaidCredentials, plaidClient, plaidCountryCodes, plaidProducts } from "../plaidClient.js";
import { safeLogEvent } from "../security.js";
import { requireSession } from "../session.js";
import {
  disconnect,
  getAccessToken,
  getCursor,
  getLastSyncedAt,
  getTransactions,
  removeTransactions,
  saveAccessToken,
  saveSyncState,
  StoredTransaction
} from "../storage.js";

export const plaidRouter = express.Router();

function friendlyCategory(transaction: any): string {
  const text = [
    transaction.personal_finance_category?.primary,
    transaction.personal_finance_category?.detailed,
    transaction.category?.join(" "),
    transaction.name,
    transaction.merchant_name
  ].filter(Boolean).join(" ").toLowerCase();
  if (text.includes("restaurant") || text.includes("grocery") || text.includes("food")) return "Food";
  if (text.includes("rent") || text.includes("mortgage")) return "Housing";
  if (text.includes("utility") || text.includes("electric") || text.includes("water")) return "Utilities";
  if (text.includes("phone") || text.includes("insurance") || text.includes("bill")) return "Bills";
  if (text.includes("gas") || text.includes("fuel") || text.includes("taxi") || text.includes("transport")) return "Transport";
  if (text.includes("shop") || text.includes("store") || text.includes("retail")) return "Shopping";
  if (text.includes("payroll") || text.includes("deposit") || text.includes("income")) return "Income";
  if (text.includes("subscription") || text.includes("streaming")) return "Subscriptions";
  if (text.includes("loan") || text.includes("credit card")) return "Debt";
  if (text.includes("saving")) return "Savings";
  return "Needs Review";
}

function normalizeTransaction(transaction: any): StoredTransaction {
  const category = friendlyCategory(transaction);
  const rawAmount = Number(transaction.amount || 0);
  const appAmount = rawAmount > 0 ? -rawAmount : Math.abs(rawAmount);
  return {
    id: transaction.transaction_id,
    source: "plaid",
    date: transaction.date,
    merchant_name: transaction.merchant_name || transaction.name,
    name: transaction.name || transaction.merchant_name || "Transaction",
    amount: appAmount,
    category,
    account_id: transaction.account_id,
    pending: transaction.pending,
    payment_channel: transaction.payment_channel,
    recurring_guess: Boolean(transaction.personal_finance_category?.detailed?.toLowerCase?.().includes("subscription")),
    needs_review: category === "Needs Review",
    plaid_raw_amount: rawAmount
  };
}

function sandboxResponse(res: express.Response) {
  return res.status(503).json({
    success: false,
    code: "PLAID_NOT_CONFIGURED",
    message: "Sandbox bank linking is not set up yet. Manual entry, CSV import, and backup restore remain available."
  });
}

plaidRouter.use(requireSession);

async function linkTokenHandler(req: express.Request, res: express.Response, next: express.NextFunction) {
  try {
    if (!hasPlaidCredentials()) return sandboxResponse(res);
    const platform = req.body?.platform === "android" ? "android" : "web";
    const redirectUri = process.env.PLAID_REDIRECT_URI?.trim();
    const request = {
      client_name: process.env.CLIENT_NAME || "Reid & Wilson Money Coach",
      products: plaidProducts(),
      country_codes: plaidCountryCodes(),
      language: "en" as const,
      user: { client_user_id: req.sessionUserId! },
      webhook: process.env.PLAID_WEBHOOK_URL || undefined,
      redirect_uri: redirectUri || undefined,
      ...(platform === "android" ? {
        android_package_name: process.env.APP_PACKAGE_NAME || "reid.wilson.moneycoach"
      } : {})
    };
    const response = await plaidClient().linkTokenCreate(request);
    res.json({ success: true, link_token: response.data.link_token, environment: process.env.PLAID_ENV || "sandbox" });
  } catch (error) {
    next(error);
  }
}

plaidRouter.post("/link-token", linkTokenHandler);
plaidRouter.post("/create_link_token", linkTokenHandler);

async function exchangeHandler(req: express.Request, res: express.Response, next: express.NextFunction) {
  try {
    if (!hasPlaidCredentials()) return sandboxResponse(res);
    const publicToken = typeof req.body?.public_token === "string" ? req.body.public_token : "";
    if (!publicToken || publicToken.length > 2048) {
      return res.status(400).json({ success: false, code: "INVALID_PUBLIC_TOKEN", message: "A valid public token is required." });
    }
    const response = await plaidClient().itemPublicTokenExchange({ public_token: publicToken });
    await saveAccessToken(req.sessionUserId!, response.data.access_token, response.data.item_id);
    res.json({ success: true, message: "Sandbox bank connected." });
  } catch (error) {
    next(error);
  }
}

plaidRouter.post("/exchange", exchangeHandler);
plaidRouter.post("/exchange_public_token", exchangeHandler);

async function transactionsSyncHandler(req: express.Request, res: express.Response, next: express.NextFunction) {
  try {
    if (!hasPlaidCredentials()) return sandboxResponse(res);
    const userId = req.sessionUserId!;
    const accessToken = await getAccessToken(userId);
    if (!accessToken) return res.status(404).json({ success: false, code: "NO_BANK_CONNECTION", message: "No bank connection found." });
    let cursor = await getCursor(userId);
    let hasMore = true;
    let pages = 0;
    const added: StoredTransaction[] = [];
    const modified: StoredTransaction[] = [];
    const removed: RemovedTransaction[] = [];
    while (hasMore && pages < 50) {
      const response = await plaidClient().transactionsSync({ access_token: accessToken, cursor, count: 100 });
      cursor = response.data.next_cursor;
      hasMore = response.data.has_more;
      added.push(...response.data.added.map(normalizeTransaction));
      modified.push(...response.data.modified.map(normalizeTransaction));
      removed.push(...response.data.removed);
      pages += 1;
    }
    if (hasMore) throw new Error("Plaid sync exceeded the safe page limit");
    if (cursor) await saveSyncState(userId, cursor, [...added, ...modified]);
    await removeTransactions(userId, removed.map((item) => item.transaction_id));
    res.json({
      success: true,
      environment: process.env.PLAID_ENV || "sandbox",
      last_synced_at: (await getLastSyncedAt(userId)) || new Date().toISOString(),
      transactions: await getTransactions(userId)
    });
  } catch (error) {
    next(error);
  }
}

plaidRouter.get("/transactions/sync", transactionsSyncHandler);
plaidRouter.get("/transactions_sync", transactionsSyncHandler);
plaidRouter.post("/sync", transactionsSyncHandler);

plaidRouter.post("/disconnect", async (req, res, next) => {
  try {
    const userId = req.sessionUserId!;
    const accessToken = await getAccessToken(userId);
    if (accessToken && hasPlaidCredentials()) await plaidClient().itemRemove({ access_token: accessToken });
    await disconnect(userId, Boolean(req.body?.deleteSyncedData));
    res.json({ success: true, message: "Bank access revoked and connection removed." });
  } catch (error) {
    next(error);
  }
});

export const plaidWebhookRouter = express.Router();

plaidWebhookRouter.post("/webhook", (req, res) => {
  safeLogEvent("plaid_webhook_received", {
    webhook_type: req.body?.webhook_type,
    webhook_code: req.body?.webhook_code
  });
  res.json({ received: true });
});
