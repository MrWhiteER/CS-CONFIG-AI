-- cs2-autoconfig cloud, D1 schema.
--
-- One account, up to three ways into it. The account is keyed by an id of its
-- own rather than by any of the three, which is what lets somebody start with
-- an email address, attach Google, attach Steam, and still be the same account
-- holding the same settings on the same plan throughout.

CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,          -- internal, never changes
  steam_id      TEXT UNIQUE,               -- 17 digits, once attached
  google_sub    TEXT UNIQUE,               -- Google's subject id
  email         TEXT UNIQUE,               -- from Google, or chosen here
  password_hash TEXT,                      -- pbkdf2$rounds$salt$hash
  tier          TEXT NOT NULL DEFAULT 'basic',
  created_at    INTEGER NOT NULL,
  last_seen_at  INTEGER
);

-- Only the hash is kept. A copy of this table is not a copy of anybody's
-- sessions, which is the point of hashing something that is only ever
-- compared and never shown.
CREATE TABLE IF NOT EXISTS sessions (
  token_hash  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS sessions_by_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_by_expiry ON sessions(expires_at);

-- A sign-in in progress: started by the launcher, finished by the browser,
-- collected by the launcher. Rows are short-lived by design -- see
-- LOGIN_WINDOW_SECONDS -- and deleted as soon as they are claimed.
--
-- `challenge` is the hash of a secret the launcher keeps. The state in this
-- table travels through the browser's address bar; the secret behind the
-- challenge never does, so a copied URL is not enough to take the session.
--
-- `link_user_id` set means this is attaching a second identity to an account
-- that already exists, rather than signing one in.
CREATE TABLE IF NOT EXISTS logins (
  state        TEXT PRIMARY KEY,
  provider     TEXT NOT NULL,              -- 'steam' or 'google'
  challenge    TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  link_user_id TEXT,
  subject      TEXT,                       -- filled in once the provider confirms
  email        TEXT
);
CREATE INDEX IF NOT EXISTS logins_by_age ON logins(created_at);

-- Somewhere to stop for an address being guessed at. Per address rather than
-- per connection: the account is what is being protected, and whatever is
-- guessing can change address between attempts.
CREATE TABLE IF NOT EXISTS login_attempts (
  email    TEXT PRIMARY KEY,
  attempts INTEGER NOT NULL DEFAULT 0,
  first_at INTEGER NOT NULL
);
