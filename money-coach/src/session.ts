import crypto from "node:crypto";
import express from "express";
import { createSessionToken, hashSessionToken } from "./security.js";
import { registerSession, userForSession } from "./storage.js";

declare global {
  namespace Express {
    interface Request {
      sessionUserId?: string;
    }
  }
}

function bearerToken(req: express.Request): string | null {
  const header = req.get("authorization") || "";
  const [scheme, token] = header.split(/\s+/, 2);
  if (scheme?.toLowerCase() !== "bearer" || !token || token.length < 32 || token.length > 256) return null;
  return token;
}

export async function requireSession(req: express.Request, res: express.Response, next: express.NextFunction) {
  try {
    const token = bearerToken(req);
    if (!token) return res.status(401).json({ success: false, code: "SESSION_REQUIRED", message: "Secure session required." });
    const userId = await userForSession(hashSessionToken(token));
    if (!userId) return res.status(401).json({ success: false, code: "SESSION_EXPIRED", message: "Start a new secure session." });
    req.sessionUserId = userId;
    next();
  } catch (error) {
    next(error);
  }
}

export async function registerSessionHandler(_req: express.Request, res: express.Response, next: express.NextFunction) {
  try {
    const token = createSessionToken();
    const userId = crypto.randomUUID();
    await registerSession(hashSessionToken(token), userId);
    res.status(201).json({ success: true, session_token: token });
  } catch (error) {
    next(error);
  }
}
