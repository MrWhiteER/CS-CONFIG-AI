# cs2-autoconfig cloud

The server half: accounts, plans, and settings that follow somebody between
machines. It is a single Cloudflare Worker over D1 (accounts) and R2
(settings).

## Why this exists at all

The launcher cannot hold a Cloudflare credential. It is a desktop application
whose source is public, and a PyInstaller bundle unpacks with a script anyone
can download — so a key shipped inside it is a published key, whatever it is
wrapped in. There is no arrangement where a binary running on somebody's own
machine keeps a secret from them.

So nothing secret is shipped. The launcher knows two things, both public:

* the address of this Worker, and
* the Google **client id**, which is public by design — it is in the sign-in
  URL every user sees.

Everything that needs a secret happens here, where the secret is not reachable
from a user's machine:

| Secret | Set with | Reaches the launcher? |
| --- | --- | --- |
| R2 and D1 | bindings in `wrangler.toml` | never — these are not keys, Cloudflare resolves them at runtime |
| `GOOGLE_CLIENT_SECRET` | `wrangler secret put` | never — only used server-side, exchanging an authorisation code |
| `ADMIN_TOKEN` | `wrangler secret put` | never — the owner holds it, see below |

## Deploying it

`wrangler` is Cloudflare's own tool and it runs on Node, which Windows does
not ship. If `wrangler` reports *"is not recognized as the name of a cmdlet"*,
that is what is missing -- not wrangler, Node.

```powershell
winget install OpenJS.NodeJS.LTS
```

Then **open a new terminal** -- the installer puts Node on the PATH and an
already-open window will not see it -- and:

```powershell
npm install -g wrangler
wrangler login
```

If you would rather not install Node at all, everything below can be done from
the Cloudflare dashboard instead; see *Without wrangler* at the end.

**1. Make the database and the bucket.**

```bash
wrangler d1 create cs2-autoconfig
wrangler r2 bucket create cs2-autoconfig-settings
```

Put the database id and bucket name into `wrangler.toml`.

**2. Create the tables.**

```bash
wrangler d1 execute cs2-autoconfig --remote --file=schema.sql
```

**3. Set the secrets.** Neither is ever written to a file in this repository.

```bash
wrangler secret put ADMIN_TOKEN
wrangler secret put GOOGLE_CLIENT_SECRET
```

Generate the admin token with something that is not a word you chose:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**4. Deploy, and set `PUBLIC_ORIGIN`** in `wrangler.toml` to the address it
reports. It has to match exactly: Steam checks the realm against the return
address, and Google only redirects to a URI registered against the client.

```bash
wrangler deploy
curl https://YOUR-WORKER-URL/health
```

## Google sign-in

In the Google Cloud console, under *APIs & Services → Credentials*, create an
**OAuth client ID** of type *Web application* with the redirect URI:

```
https://YOUR-WORKER-URL/auth/google/return
```

Put the **client id** into `wrangler.toml` (`GOOGLE_CLIENT_ID`) and into the
launcher's `cs2cfg/cloudconfig.py`; put the **client secret** into
`wrangler secret put GOOGLE_CLIENT_SECRET`. Leaving `GOOGLE_CLIENT_ID` empty
turns Google sign-in off, which is what a launcher pointed at a
half-configured server should find.

Steam needs no registration and no key — its OpenID is open.

## Running the plans

Plans are set here and nowhere else. The launcher is public source and can be
edited to claim anything; what editing it cannot do is make this answer
differently.

```bash
# Who exists
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://YOUR-WORKER-URL/admin/users

# Put somebody on a plan, named by whichever identity you have to hand
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "content-type: application/json" \
     -d '{"steam_id":"76561198000000000","tier":"ultimate"}' \
     https://YOUR-WORKER-URL/admin/tier
```

Sessions carry no plan of their own, so a change takes effect on the user's
next request rather than their next sign-in.

`ENTITLEMENTS` at the top of `src/index.js` decides what each plan may do. All
three are currently identical and permissive: the machinery is in place and
the split is not decided, so nothing is withheld from anybody yet. Moving a
capability out of `basic` is the whole act of putting it behind a plan.

## The shape of a sign-in

Three ways in — Steam, Google, email and password — to one account. Steam is
the end of every road: a CS2 configuration without a Steam account is a
configuration for nobody, so an account that has not attached one reports
`needs_steam` and the launcher walks through attaching it.

The two browser flows go:

```
launcher  POST /auth/start   { provider, challenge } -> { state, url }
browser   GET  url                                   -> Steam or Google
provider  GET  /auth/<p>/return?state=...            -> verified here
launcher  POST /auth/claim   { state, verifier }     -> { token, ... }
```

The state travels through the browser's address bar, so it is not treated as a
secret. The verifier never leaves the launcher; only its hash goes up front.
Someone who copies the return URL out of the browser still cannot take the
session.

## Routes

| Route | Needs | Does |
| --- | --- | --- |
| `GET /health` | — | liveness, and whether Google is configured |
| `POST /auth/start` | — | begin a Steam or Google sign-in |
| `GET /auth/steam/return` | — | Steam comes back here |
| `GET /auth/google/return` | — | Google comes back here |
| `POST /auth/claim` | — | collect the session the browser earned |
| `POST /auth/password/register` | — | open an account with an address and password |
| `POST /auth/password/login` | — | sign in with one |
| `GET /me` | session | who, which plan, what is still missing |
| `POST /auth/link/start` | session | attach Steam or Google to this account |
| `POST /auth/link/password` | session | attach an address and password |
| `POST /auth/logout` | session | end this session |
| `GET/PUT/DELETE /settings` | session + `sync` | the settings blob, per account |
| `GET /admin/users` | admin token | everyone |
| `POST /admin/tier` | admin token | set somebody's plan |

## What is deliberately not here

**Email verification and password reset.** Both need somewhere to send email,
which Cloudflare does not provide on its own. Until that is wired up, an email
address is an identifier and a password is a password, and neither is proof
that somebody owns the address. Worth knowing before treating the address as
one.

**A rate limiter in front.** `login_attempts` stops an address being guessed at
overnight; it is a floor, not a replacement for a real rule at the edge.

## Without wrangler

Nothing here needs a terminal. The same four steps, in the dashboard:

1. **D1** -- *Storage & Databases -> D1 -> Create*. Call it `cs2-autoconfig`,
   open it, and paste `schema.sql` into the console.
2. **R2** -- *R2 -> Create bucket*. Any name; it goes in `wrangler.toml`.
3. **The Worker** -- *Workers & Pages -> Create -> Start from Hello World*,
   then replace the code with `src/index.js`. Under *Settings -> Bindings*,
   add `DB` pointing at the D1 database and `BUCKET` at the R2 bucket.
4. **The secrets** -- *Settings -> Variables and Secrets*. Add `ADMIN_TOKEN`
   and `GOOGLE_CLIENT_SECRET` as **secrets**, not plain text, and
   `PUBLIC_ORIGIN` and `GOOGLE_CLIENT_ID` as ordinary variables.

The dashboard route is slower to repeat but has one real advantage: a secret
added there was never on your machine and never in a shell history.
