import "dotenv/config";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import cors from "cors";
import express from "express";
import helmet from "helmet";
import { hasPlaidCredentials, plaidClient } from "./plaidClient.js";
import { plaidRouter, plaidWebhookRouter } from "./routes/plaid.js";
import { rateLimit } from "./rateLimit.js";
import { registerSessionHandler, requireSession } from "./session.js";
import { safeLogEvent } from "./security.js";
import { deleteUserData, getAccessToken, initializeStorage, storageMode } from "./storage.js";

const app = express();
const port = Number(process.env.PORT || 8787);
const publicDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../public");
const defaultOrigins = [
  "https://reidandwilson.com",
  "https://www.reidandwilson.com",
  "https://app.reidandwilson.com",
  "https://api.reidandwilson.com",
  "https://reid-wilson-money-coach.onrender.com",
  process.env.RENDER_EXTERNAL_URL || ""
];
const allowedOrigins = new Set(
  [...defaultOrigins, ...(process.env.ALLOWED_ORIGINS || "").split(",")]
    .map((value) => value.trim().replace(/\/$/, ""))
    .filter(Boolean)
);

app.disable("x-powered-by");
app.set("trust proxy", 1);
app.use((req, res, next) => {
  res.locals.requestId = crypto.randomUUID();
  res.setHeader("X-Request-ID", res.locals.requestId);
  next();
});
app.use(helmet({
  frameguard: false,
  crossOriginEmbedderPolicy: false,
  crossOriginResourcePolicy: { policy: "cross-origin" },
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      baseUri: ["'self'"],
      objectSrc: ["'none'"],
      formAction: ["'self'"],
      scriptSrc: ["'self'", "https://cdn.plaid.com"],
      styleSrc: ["'self'"],
      imgSrc: ["'self'", "data:"],
      connectSrc: ["'self'", "https://*.plaid.com"],
      frameSrc: ["https://*.plaid.com"],
      frameAncestors: ["'self'", "https://reidandwilson.com", "https://www.reidandwilson.com", "https://*.wix.com", "https://*.wixsite.com"],
      upgradeInsecureRequests: null
    }
  },
  referrerPolicy: { policy: "strict-origin-when-cross-origin" }
}));
app.use((req, res, next) => {
  res.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()");
  if (process.env.NODE_ENV === "production") res.setHeader("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  next();
});
app.use(cors({
  origin(origin, callback) {
    if (!origin || allowedOrigins.has(origin.replace(/\/$/, ""))) return callback(null, true);
    if (process.env.NODE_ENV !== "production" && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return callback(null, true);
    callback(new Error("Origin not allowed"));
  },
  methods: ["GET", "POST", "DELETE", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization"],
  maxAge: 600
}));
app.use(express.json({ limit: "256kb" }));
app.use(rateLimit(60_000, 120));

function healthPayload() {
  return {
    ok: true,
    service: "reid-wilson-money-coach",
    version: "2.3.26080302",
    storage: storageMode(),
    plaid_environment: process.env.PLAID_ENV || "sandbox",
    plaid_configured: hasPlaidCredentials()
  };
}

app.get("/health", (_req, res) => res.json(healthPayload()));
app.get("/api/health", (_req, res) => res.json(healthPayload()));
app.post("/api/session/register", rateLimit(60_000, 10), registerSessionHandler);
app.use("/api/plaid", plaidRouter);
app.use("/api/plaid", plaidWebhookRouter);

app.delete("/api/session/data", requireSession, async (req, res, next) => {
  try {
    const userId = req.sessionUserId!;
    const accessToken = await getAccessToken(userId);
    if (accessToken && hasPlaidCredentials()) await plaidClient().itemRemove({ access_token: accessToken });
    await deleteUserData(userId);
    res.json({ success: true, message: "Server-side Money Coach data deleted." });
  } catch (error) {
    next(error);
  }
});

app.use(express.static(publicDir, {
  extensions: ["html"],
  etag: true,
  maxAge: process.env.NODE_ENV === "production" ? "1h" : 0,
  setHeaders(res, filePath) {
    if (filePath.endsWith("service-worker.js") || filePath.endsWith("index.html")) res.setHeader("Cache-Control", "no-cache");
  }
}));
app.get("/", (_req, res) => res.sendFile(path.join(publicDir, "index.html")));
app.use("/api", (_req, res) => res.status(404).json({ success: false, code: "NOT_FOUND", message: "API route not found." }));
app.get("*", (_req, res) => res.sendFile(path.join(publicDir, "index.html")));

app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  const requestId = res.locals.requestId || crypto.randomUUID();
  safeLogEvent("request_failed", { request_id: requestId, error_type: error instanceof Error ? error.name : "UnknownError" });
  if (!res.headersSent) {
    res.status(500).json({
      success: false,
      code: "SERVER_ERROR",
      message: "We could not complete that request. Manual entry and CSV tools are still available.",
      request_id: requestId
    });
  }
});

initializeStorage()
  .then(() => {
    app.listen(port, () => safeLogEvent("service_started", { port, storage: storageMode() }));
  })
  .catch((error) => {
    safeLogEvent("service_start_failed", { error_type: error instanceof Error ? error.name : "UnknownError" });
    process.exitCode = 1;
  });
