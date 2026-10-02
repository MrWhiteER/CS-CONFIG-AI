/**
 * cs2-autoconfig cloud: accounts, entitlements and settings.
 *
 * This exists because the launcher cannot be trusted with a Cloudflare
 * credential. It is a desktop application whose source is public, so anything
 * shipped inside it is readable by anyone who wants it. Everything needing a
 * secret happens here instead, and the launcher only ever holds a session
 * token scoped to one person.
 *
 * Accounts
 * --------
 *
 * One account, up to three ways into it: Steam, Google, and an email address
 * with a password. Any of them signs you in to the same account, and whichever
 * you used, you land on the same settings and the same plan.
 *
 * The account is keyed by an id of its own rather than by either identity.
 * That is what lets somebody start with Google, attach Steam later, and keep
 * everything they already had -- and it is why settings are filed under that
 * id and not under a Steam id that may not exist yet.
 *
 * Steam is the end of every road. A CS2 configuration without a Steam account
 * is a configuration for nobody, so an account that has not attached one is
 * signed in but incomplete: it says `needs_steam`, and the launcher walks
 * through attaching Steam before it will do anything that needs one. Starting
 * with Google or with an email address is a way in, not a way around it.
 *
 * Signing in is a browser round trip, because both protocols are browser
 * protocols. The launcher never sees the browser's side of it:
 *
 *   launcher  POST /auth/start   { provider, challenge } -> { state, url }
 *   browser   GET  url                                   -> Steam or Google
 *   provider  GET  /auth/<p>/return?state=...            -> verified here
 *   launcher  POST /auth/claim   { state, verifier }     -> { token, ... }
 *
 * The state travels through the browser's address bar, so it is not treated
 * as a secret. The verifier never leaves the launcher; only its hash is sent
 * up front. Someone who copies the return URL out of the browser still cannot
 * take the session, because they do not have the verifier.
 */

const STEAM_OPENID = "https://steamcommunity.com/openid/login";
const STEAM_CLAIMED_ID = /^https:\/\/steamcommunity\.com\/openid\/id\/(\d{17})$/;

const GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN = "https://oauth2.googleapis.com/token";

// A sign-in has to be finished while somebody is sitting at the machine.
const LOGIN_WINDOW_SECONDS = 15 * 60;
const SESSION_DAYS = 90;

// Settings are configuration, not content, so they are small by nature. The
// cap is here so a bug in the launcher cannot fill the bucket.
const MAX_SETTINGS_BYTES = 256 * 1024;

const TIERS = ["basic", "pro", "ultimate"];

// PBKDF2 because it is what WebCrypto offers here -- there is no bcrypt or
// argon2 in a Worker. The count is OWASP's figure for PBKDF2-HMAC-SHA256 and
// is deliberately expensive; it runs natively, so it costs little wall time.
const PBKDF2_ROUNDS = 210000;
const MIN_PASSWORD = 10;

// Somewhere to stop, for an address being guessed at. Not a substitute for a
// real rate limiter in front of the Worker, and not pretending to be one: it
// is the floor, so that an unattended account is not guessable overnight.
const MAX_ATTEMPTS = 8;
const LOCKOUT_SECONDS = 15 * 60;

/**
 * What each tier may do.
 *
 * All-permissive for now: the machinery is in place and the split is not
 * decided, so nothing is withheld from anybody yet. Moving a capability out
 * of `basic` is the whole act of putting it behind a tier.
 *
 * Decided here rather than in the launcher because the launcher is public
 * source and can be edited to claim anything. What editing it cannot do is
 * make this answer differently -- which is why the things genuinely worth
 * gating are the ones this side does the work for, sync being the first.
 */
const EVERYTHING = ["configure", "launch", "fixit", "crosshairx", "keyboard",
                    "scripts", "demos", "faceit", "sync"];
const ENTITLEMENTS = { basic: EVERYTHING, pro: EVERYTHING, ultimate: EVERYTHING };

// --- small helpers ----------------------------------------------------------

const now = () => Math.floor(Date.now() / 1000);

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

const fail = (status, error) => json({ ok: false, error }, status);

function randomToken(bytes = 32) {
  const raw = crypto.getRandomValues(new Uint8Array(bytes));
  return [...raw].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hashPassword(password, salt = null, rounds = PBKDF2_ROUNDS) {
  const useSalt = salt || randomToken(16);
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt: new TextEncoder().encode(useSalt),
      iterations: rounds, hash: "SHA-256" },
    key, 256);
  const hex = [...new Uint8Array(bits)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `pbkdf2$${rounds}$${useSalt}$${hex}`;
}

async function passwordMatches(password, stored) {
  const parts = String(stored || "").split("$");
  if (parts.length !== 4 || parts[0] !== "pbkdf2") return false;
  const rounds = Number(parts[1]);
  if (!Number.isFinite(rounds) || rounds < 1000) return false;
  return sameSecret(await hashPassword(password, parts[2], rounds), stored);
}

const tidyEmail = (value) => String(value || "").trim().toLowerCase();
const looksLikeEmail = (value) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value);

/** Compare without leaking how much of the string matched. */
function sameSecret(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let differences = 0;
  for (let i = 0; i < a.length; i++) differences |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return differences === 0;
}

function page(title, message) {
  // Plain and self-closing. Nobody wants to read a web page here; they want
  // to go back to the application they were already using.
  return new Response(
    `<!doctype html><meta charset="utf-8"><title>${title}</title>` +
    `<style>body{background:#07050d;color:#ece8f7;font:16px/1.6 "Segoe UI",Arial,sans-serif;` +
    `display:grid;place-items:center;height:100vh;margin:0;text-align:center}` +
    `p{color:#a78bfa;margin:.4rem 0 0}</style>` +
    `<div><h1>${title}</h1><p>${message}</p></div>`,
    { status: 200, headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

const originOf = (env, url) => env.PUBLIC_ORIGIN || url.origin;

// --- the two providers ------------------------------------------------------

/**
 * Check a Steam OpenID assertion with Steam itself.
 *
 * The parameters arrive through the browser, so none of them can be believed
 * until Steam says so. This is that step: the whole set goes back with mode
 * `check_authentication`, and only `is_valid:true` counts. Skipping it would
 * let anyone sign in as anyone by editing a query string.
 */
async function verifySteam(params) {
  const body = new URLSearchParams();
  for (const [key, value] of params) {
    if (key.startsWith("openid.")) body.set(key, value);
  }
  body.set("openid.mode", "check_authentication");

  const answer = await fetch(STEAM_OPENID, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!answer.ok) return null;
  if (!/is_valid\s*:\s*true/i.test(await answer.text())) return null;

  const found = STEAM_CLAIMED_ID.exec(params.get("openid.claimed_id") || "");
  return found ? { subject: found[1], email: null } : null;
}

/**
 * Exchange Google's authorisation code for the identity behind it.
 *
 * The id token is read without checking its signature, which is correct here
 * and nowhere else: it came back over TLS from Google's token endpoint, in
 * answer to a request carrying this Worker's own client secret. It did not
 * come through the browser, so there is nothing in the path to have forged
 * it. An id token arriving by any other route would have to be verified.
 */
async function verifyGoogle(env, url, code) {
  if (!env.GOOGLE_CLIENT_ID || !env.GOOGLE_CLIENT_SECRET) return null;

  const answer = await fetch(GOOGLE_TOKEN, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: `${originOf(env, url)}/auth/google/return`,
      grant_type: "authorization_code",
    }).toString(),
  });
  if (!answer.ok) return null;

  const payload = await answer.json();
  const token = String(payload.id_token || "");
  const middle = token.split(".")[1];
  if (!middle) return null;

  try {
    const claims = JSON.parse(
      atob(middle.replace(/-/g, "+").replace(/_/g, "/")),
    );
    if (!claims.sub) return null;
    // An unverified address is not an address anybody should be found by.
    return { subject: String(claims.sub), email: claims.email_verified ? claims.email : null };
  } catch {
    return null;
  }
}

function authorizeUrl(provider, env, url, state) {
  const origin = originOf(env, url);
  if (provider === "steam") {
    const openid = new URLSearchParams({
      "openid.ns": "http://specs.openid.net/auth/2.0",
      "openid.mode": "checkid_setup",
      "openid.return_to": `${origin}/auth/steam/return?state=${state}`,
      "openid.realm": origin,
      "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
      "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    });
    return `${STEAM_OPENID}?${openid}`;
  }
  const google = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID || "",
    redirect_uri: `${origin}/auth/google/return`,
    response_type: "code",
    scope: "openid email",
    state,
    // So somebody with several Google accounts is asked which, rather than
    // being silently signed in as whichever the browser saw last.
    prompt: "select_account",
  });
  return `${GOOGLE_AUTH}?${google}`;
}

// --- accounts ---------------------------------------------------------------

const COLUMN = { steam: "steam_id", google: "google_sub" };

async function userByIdentity(env, provider, subject) {
  return env.DB.prepare(
    `SELECT * FROM users WHERE ${COLUMN[provider]} = ?`,
  ).bind(subject).first();
}

async function userById(env, id) {
  return env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(id).first();
}

/** Find the account behind an identity, or open one. */
async function resolveUser(env, provider, subject, email) {
  const found = await userByIdentity(env, provider, subject);
  if (found) {
    if (email && !found.email) {
      await env.DB.prepare("UPDATE users SET email = ? WHERE id = ?")
        .bind(email, found.id).run();
    }
    return found;
  }

  const id = randomToken(16);
  await env.DB.prepare(
    `INSERT INTO users (id, ${COLUMN[provider]}, email, tier, created_at, last_seen_at)
     VALUES (?, ?, ?, 'basic', ?, ?)`,
  ).bind(id, subject, email, now(), now()).run();
  return userById(env, id);
}

/**
 * Attach a second way in to an account that already exists.
 *
 * The refusal matters more than the success. If the identity already belongs
 * to a different account, this stops rather than merging the two: a merge
 * would have to decide whose settings and whose plan survive, and getting
 * that wrong destroys something somebody paid for. Saying so and leaving both
 * accounts intact is recoverable; quietly picking one is not.
 */
async function linkIdentity(env, userId, provider, subject, email) {
  const holder = await userByIdentity(env, provider, subject);
  if (holder && holder.id !== userId) {
    return { ok: false, error: `that ${provider} account is already attached to another sign-in` };
  }
  if (holder) return { ok: true, already: true };

  const user = await userById(env, userId);
  if (!user) return { ok: false, error: "no such account" };
  if (user[COLUMN[provider]]) {
    return { ok: false, error: `this account already has a ${provider} sign-in attached` };
  }

  await env.DB.prepare(
    `UPDATE users SET ${COLUMN[provider]} = ?, email = COALESCE(email, ?) WHERE id = ?`,
  ).bind(subject, email, userId).run();
  return { ok: true, already: false };
}

/** The caller, from the bearer token, or null. */
async function whoever(request, env) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!token) return null;

  const hash = await sha256(token);
  const row = await env.DB.prepare(
    "SELECT s.expires_at, u.* FROM sessions s JOIN users u ON u.id = s.user_id " +
    "WHERE s.token_hash = ?",
  ).bind(hash).first();
  if (!row) return null;

  if (row.expires_at <= now()) {
    await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(hash).run();
    return null;
  }
  return row;
}

function describe(user) {
  return {
    ok: true,
    account_id: user.id,
    steam_id: user.steam_id || null,
    google: Boolean(user.google_sub),
    email: user.email || null,
    password: Boolean(user.password_hash),
    tier: user.tier,
    entitlements: ENTITLEMENTS[user.tier] || ENTITLEMENTS.basic,
    // A CS2 configuration without a Steam account is a configuration for
    // nobody, so this is the one gap the launcher has to close.
    needs_steam: !user.steam_id,
  };
}

async function newSession(env, userId) {
  const token = randomToken(32);
  const expires = now() + SESSION_DAYS * 86400;
  await env.DB.prepare(
    "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
  ).bind(await sha256(token), userId, now(), expires).run();
  return { token, expires };
}

// --- routes -----------------------------------------------------------------

async function startFlow(request, env, url, linkUserId) {
  const body = await request.json().catch(() => ({}));
  const provider = String(body.provider || "steam");
  const challenge = String(body.challenge || "");

  if (!COLUMN[provider]) return fail(400, "provider must be steam or google");
  if (!/^[0-9a-f]{64}$/.test(challenge)) {
    return fail(400, "challenge must be a sha256 hex digest");
  }
  if (provider === "google" && !env.GOOGLE_CLIENT_ID) {
    return fail(503, "Google sign-in is not configured on this server");
  }

  const state = randomToken(16);
  await env.DB.prepare(
    "INSERT INTO logins (state, provider, challenge, created_at, link_user_id) " +
    "VALUES (?, ?, ?, ?, ?)",
  ).bind(state, provider, challenge, now(), linkUserId || null).run();

  return json({ ok: true, state, url: authorizeUrl(provider, env, url, state) });
}

async function providerReturn(request, env, url, provider) {
  const state = url.searchParams.get("state") || "";
  const pending = await env.DB.prepare(
    "SELECT * FROM logins WHERE state = ? AND provider = ?",
  ).bind(state, provider).first();

  if (!pending) return page("That sign-in has expired", "Start again from the launcher.");
  if (now() - pending.created_at > LOGIN_WINDOW_SECONDS) {
    await env.DB.prepare("DELETE FROM logins WHERE state = ?").bind(state).run();
    return page("That sign-in has expired", "Start again from the launcher.");
  }

  const identity = provider === "steam"
    ? await verifySteam(url.searchParams)
    : await verifyGoogle(env, url, url.searchParams.get("code") || "");

  if (!identity) {
    const who = provider === "steam" ? "Steam" : "Google";
    return page(`${who} could not confirm that`, "Nothing has been signed in.");
  }

  await env.DB.prepare("UPDATE logins SET subject = ?, email = ? WHERE state = ?")
    .bind(identity.subject, identity.email, state).run();

  return page(
    pending.link_user_id ? "Account attached" : "Signed in",
    "You can close this tab and go back to the launcher.",
  );
}

async function claim(request, env) {
  const body = await request.json().catch(() => ({}));
  const state = String(body.state || "");
  const verifier = String(body.verifier || "");

  const pending = await env.DB.prepare("SELECT * FROM logins WHERE state = ?")
    .bind(state).first();
  if (!pending) return fail(404, "no such sign-in");

  if (now() - pending.created_at > LOGIN_WINDOW_SECONDS) {
    await env.DB.prepare("DELETE FROM logins WHERE state = ?").bind(state).run();
    return fail(410, "that sign-in expired");
  }
  // Still in the browser. Not an error -- the launcher is polling.
  if (!pending.subject) return json({ ok: true, waiting: true });

  // The state was in the address bar; the verifier never was. This is what
  // stops somebody who copied the URL out of the browser taking the session.
  if (!sameSecret(await sha256(verifier), pending.challenge)) {
    return fail(403, "that is not the launcher that started this sign-in");
  }
  await env.DB.prepare("DELETE FROM logins WHERE state = ?").bind(state).run();

  // Attaching a second identity to an account that is already signed in.
  if (pending.link_user_id) {
    const linked = await linkIdentity(
      env, pending.link_user_id, pending.provider, pending.subject, pending.email);
    if (!linked.ok) return fail(409, linked.error);
    const user = await userById(env, pending.link_user_id);
    return json({ ok: true, waiting: false, linked: true, ...describe(user) });
  }

  const user = await resolveUser(env, pending.provider, pending.subject, pending.email);
  const session = await newSession(env, user.id);
  return json({
    ok: true,
    waiting: false,
    linked: false,
    token: session.token,
    expires_at: session.expires,
    ...describe(user),
  });
}

/**
 * Whether this address has been guessed at too often lately.
 *
 * Counted per address rather than per connection, because the thing being
 * protected is one account and the thing doing the guessing can change
 * address between attempts.
 */
async function lockedOut(env, email) {
  const row = await env.DB.prepare(
    "SELECT attempts, first_at FROM login_attempts WHERE email = ?",
  ).bind(email).first();
  if (!row) return false;
  if (now() - row.first_at > LOCKOUT_SECONDS) {
    await env.DB.prepare("DELETE FROM login_attempts WHERE email = ?").bind(email).run();
    return false;
  }
  return row.attempts >= MAX_ATTEMPTS;
}

async function noteFailure(env, email) {
  await env.DB.prepare(
    "INSERT INTO login_attempts (email, attempts, first_at) VALUES (?, 1, ?) " +
    "ON CONFLICT(email) DO UPDATE SET attempts = attempts + 1",
  ).bind(email, now()).run();
}

const clearFailures = (env, email) =>
  env.DB.prepare("DELETE FROM login_attempts WHERE email = ?").bind(email).run();

async function registerWithPassword(request, env) {
  const body = await request.json().catch(() => ({}));
  const email = tidyEmail(body.email);
  const password = String(body.password || "");

  if (!looksLikeEmail(email)) return fail(400, "that does not look like an email address");
  if (password.length < MIN_PASSWORD) {
    return fail(400, `a password needs at least ${MIN_PASSWORD} characters`);
  }

  const taken = await env.DB.prepare("SELECT id FROM users WHERE email = ?")
    .bind(email).first();
  if (taken) return fail(409, "there is already an account for that address");

  const id = randomToken(16);
  await env.DB.prepare(
    "INSERT INTO users (id, email, password_hash, tier, created_at, last_seen_at) " +
    "VALUES (?, ?, ?, 'basic', ?, ?)",
  ).bind(id, email, await hashPassword(password), now(), now()).run();

  const user = await userById(env, id);
  const session = await newSession(env, id);
  return json({
    ok: true, token: session.token, expires_at: session.expires, ...describe(user),
  });
}

async function signInWithPassword(request, env) {
  const body = await request.json().catch(() => ({}));
  const email = tidyEmail(body.email);
  const password = String(body.password || "");

  if (await lockedOut(env, email)) {
    return fail(429, "too many attempts; wait a few minutes and try again");
  }

  const user = await env.DB.prepare("SELECT * FROM users WHERE email = ?")
    .bind(email).first();

  // One answer for "no such address" and for "wrong password", so this cannot
  // be used to find out which addresses have accounts.
  if (!user || !user.password_hash || !(await passwordMatches(password, user.password_hash))) {
    await noteFailure(env, email);
    return fail(401, "that email address and password do not match");
  }

  await clearFailures(env, email);
  const session = await newSession(env, user.id);
  return json({
    ok: true, token: session.token, expires_at: session.expires, ...describe(user),
  });
}

/** Attach an address and password to an account signed in some other way. */
async function addPassword(request, env, user) {
  const body = await request.json().catch(() => ({}));
  const email = tidyEmail(body.email);
  const password = String(body.password || "");

  if (!looksLikeEmail(email)) return fail(400, "that does not look like an email address");
  if (password.length < MIN_PASSWORD) {
    return fail(400, `a password needs at least ${MIN_PASSWORD} characters`);
  }
  if (user.password_hash) return fail(409, "this account already has a password");

  const taken = await env.DB.prepare("SELECT id FROM users WHERE email = ? AND id != ?")
    .bind(email, user.id).first();
  if (taken) return fail(409, "that address is already attached to another account");

  await env.DB.prepare("UPDATE users SET email = ?, password_hash = ? WHERE id = ?")
    .bind(email, await hashPassword(password), user.id).run();
  return json({ ok: true, ...describe(await userById(env, user.id)) });
}

async function settings(request, env, user) {
  // Filed under the account's own id, not under Steam's: an account that
  // started with Google has no Steam id yet, and attaching one later must not
  // move anybody's settings out from under them.
  const key = `settings/${user.id}.json`;

  if (request.method === "GET") {
    const held = await env.BUCKET.get(key);
    if (!held) return json({ ok: true, found: false, settings: null });
    return json({
      ok: true,
      found: true,
      updated_at: held.customMetadata?.updated_at || null,
      settings: JSON.parse(await held.text()),
    });
  }

  if (request.method === "PUT") {
    const raw = await request.text();
    if (raw.length > MAX_SETTINGS_BYTES) {
      return fail(413, `settings are limited to ${MAX_SETTINGS_BYTES} bytes`);
    }
    try {
      JSON.parse(raw);
    } catch {
      return fail(400, "settings must be JSON");
    }
    const stamp = String(now());
    await env.BUCKET.put(key, raw, {
      httpMetadata: { contentType: "application/json" },
      customMetadata: { updated_at: stamp, account: user.id },
    });
    return json({ ok: true, updated_at: stamp });
  }

  if (request.method === "DELETE") {
    await env.BUCKET.delete(key);
    return json({ ok: true, deleted: true });
  }

  return fail(405, "method not allowed");
}

/**
 * The owner's door.
 *
 * Behind a secret held in the Worker's environment and never in the launcher.
 * This is the only way a tier changes, which is what the plans being given
 * out by the owner has to mean if it is to mean anything.
 */
async function admin(request, env, url) {
  const offered = (request.headers.get("authorization") || "").replace(/^Bearer /, "");
  if (!env.ADMIN_TOKEN || !sameSecret(offered, env.ADMIN_TOKEN)) return fail(403, "no");

  if (request.method === "GET" && url.pathname === "/admin/users") {
    const { results } = await env.DB.prepare(
      "SELECT id, steam_id, google_sub, email, tier, created_at, last_seen_at " +
      "FROM users ORDER BY created_at DESC LIMIT 500",
    ).all();
    return json({ ok: true, users: results });
  }

  if (request.method === "POST" && url.pathname === "/admin/tier") {
    const body = await request.json().catch(() => ({}));
    const tier = String(body.tier || "");
    if (!TIERS.includes(tier)) return fail(400, `tier must be one of ${TIERS.join(", ")}`);

    // Named by whichever identity the owner has to hand.
    let user = null;
    if (body.account_id) user = await userById(env, String(body.account_id));
    else if (body.steam_id) user = await userByIdentity(env, "steam", String(body.steam_id));
    else if (body.email) {
      user = await env.DB.prepare("SELECT * FROM users WHERE email = ?")
        .bind(String(body.email)).first();
    }
    if (!user) return fail(404, "no account matched that");

    await env.DB.prepare("UPDATE users SET tier = ? WHERE id = ?").bind(tier, user.id).run();
    // Sessions carry no tier of their own, so this takes effect immediately.
    return json({ ok: true, account_id: user.id, tier });
  }

  return fail(404, "no such admin route");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    try {
      if (path === "/health") return json({ ok: true, google: Boolean(env.GOOGLE_CLIENT_ID) });

      if (path === "/auth/start" && request.method === "POST") {
        return await startFlow(request, env, url, null);
      }
      if (path === "/auth/steam/return") return await providerReturn(request, env, url, "steam");
      if (path === "/auth/google/return") return await providerReturn(request, env, url, "google");
      if (path === "/auth/claim" && request.method === "POST") return await claim(request, env);
      if (path === "/auth/password/register" && request.method === "POST") {
        return await registerWithPassword(request, env);
      }
      if (path === "/auth/password/login" && request.method === "POST") {
        return await signInWithPassword(request, env);
      }
      if (path.startsWith("/admin/")) return await admin(request, env, url);

      // Everything past here needs a session.
      const user = await whoever(request, env);
      if (!user) return fail(401, "sign in first");

      if (path === "/me") {
        await env.DB.prepare("UPDATE users SET last_seen_at = ? WHERE id = ?")
          .bind(now(), user.id).run();
        return json(describe(user));
      }

      // Attaching another way in, from inside a session.
      if (path === "/auth/link/start" && request.method === "POST") {
        return await startFlow(request, env, url, user.id);
      }
      if (path === "/auth/link/password" && request.method === "POST") {
        return await addPassword(request, env, user);
      }

      if (path === "/settings") {
        if (!(ENTITLEMENTS[user.tier] || []).includes("sync")) {
          return fail(402, "settings sync is not included in this plan");
        }
        return await settings(request, env, user);
      }

      if (path === "/auth/logout" && request.method === "POST") {
        const token = (request.headers.get("authorization") || "").replace(/^Bearer /, "");
        await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?")
          .bind(await sha256(token)).run();
        return json({ ok: true });
      }

      return fail(404, "no such route");
    } catch (err) {
      // Never hand an internal message to a client that cannot use it.
      console.error(err && err.stack ? err.stack : String(err));
      return fail(500, "something went wrong here");
    }
  },
};
