import express from "express";

type Bucket = { count: number; resetAt: number };

export function rateLimit(windowMs: number, limit: number): express.RequestHandler {
  const buckets = new Map<string, Bucket>();
  let requests = 0;
  return (req, res, next) => {
    const now = Date.now();
    const key = req.ip || req.socket.remoteAddress || "unknown";
    const current = buckets.get(key);
    const bucket = !current || current.resetAt <= now ? { count: 0, resetAt: now + windowMs } : current;
    bucket.count += 1;
    buckets.set(key, bucket);
    res.setHeader("RateLimit-Limit", String(limit));
    res.setHeader("RateLimit-Remaining", String(Math.max(0, limit - bucket.count)));
    res.setHeader("RateLimit-Reset", String(Math.ceil(bucket.resetAt / 1000)));
    if (bucket.count > limit) {
      res.setHeader("Retry-After", String(Math.max(1, Math.ceil((bucket.resetAt - now) / 1000))));
      res.status(429).json({ success: false, code: "RATE_LIMITED", message: "Please wait a moment and try again." });
      return;
    }
    requests += 1;
    if (requests % 500 === 0) {
      for (const [storedKey, stored] of buckets) if (stored.resetAt <= now) buckets.delete(storedKey);
    }
    next();
  };
}
