import { TRUSTED_IP_HEADERS } from "@reactive-resume/utils/rate-limit";

// ponytail: in-memory per-process dedup window. Single-instance is the default deploy; for
// multi-instance, swap the Map for a Redis SETNX+EXPIRE keyed the same way (REDIS_URL already
// exists in env). Upgrade only if you scale out — each instance dedups independently otherwise.
const WINDOW_MS = 60 * 60 * 1000; // 1 hour
const MAX_ENTRIES = 50_000; // bound the Map; prune expired entries before growing past this.

const seen = new Map<string, number>(); // key -> expiry timestamp

/**
 * Returns `true` at most once per `key` per window. `now` is a parameter (not `Date.now()`)
 * so callers stay testable with a driven clock.
 */
export function shouldCountView(key: string, now: number): boolean {
	const expiry = seen.get(key);
	if (expiry !== undefined && expiry > now) return false;

	if (seen.size >= MAX_ENTRIES) {
		for (const [k, exp] of seen) {
			if (exp <= now) seen.delete(k);
		}
	}

	seen.set(key, now + WINDOW_MS);
	return true;
}

// Mirrors the rate-limit middleware's client-key derivation so dedup and rate limiting agree on
// "who is this viewer": trusted proxy IP first, then a user-agent + language fingerprint fallback.
export function clientKeyFromHeaders(headers: Headers): string {
	for (const headerName of TRUSTED_IP_HEADERS) {
		const raw = headers.get(headerName)?.trim();
		if (!raw) continue;

		// Some proxies provide a comma-delimited chain; the first item is the original client.
		const ip = raw.split(",")[0]?.trim();
		if (ip) return `ip:${ip}`;
	}

	const userAgent = headers.get("user-agent")?.trim() ?? "unknown";
	const language = headers.get("accept-language")?.split(",")[0]?.trim() ?? "none";

	return `fp:${userAgent.slice(0, 64)}:${language.slice(0, 16)}`;
}
