# Hark Daily (`Morning_Brief`) — Full Repository Security & Data Risk Audit

**Last Updated:** November 11, 2026 (Post-Commit `b368cfb` Verification + Phase 3 Fresh Deep Audit)  
**Scope:** Full repository (`web/`, `web/api/`, `app/`, `voice_service/`, `android/`, `ios/`, `scripts/`, `supabase/`, `.github/workflows/`, and Git history)

---

## 1. Phase 1 Remediation Review (Verification of Commit `5b03088`)

We reviewed commit `5b03088` (`fix(security): resolve all critical, high, and medium audit findings (SEC-01 - SEC-14)`) and commit `b368cfb` (`fix(security): resolve phase 2 security and data risks (SEC-15 - SEC-24, DATA-01 - DATA-07)`). All 14 Phase 1 items are verified resolved:

| ID | Original Severity | Original Finding | Commit `5b03088` Verification Status |
| :--- | :--- | :--- | :--- |
| **SEC-01** | 🔴 **Critical** | Hardcoded Discord Webhook URL in Git History & Remote Branch | ✅ **Resolved** (`origin/feature/hamburger-menu-account-coffee-feedback` deleted; webhook moved to env var) |
| **SEC-02** | 🔴 **Critical** | Unauthenticated & Unthrottled Discord Feedback Proxy | ✅ **Resolved** (Hardened in Phase 2 via SEC-15 & SEC-24: strictly requires verified Supabase user, trusted origins, authoritative IP) |
| **SEC-03** | 🟠 **High** | SSRF Blocklist Bypass & Open CORS Proxy in `/api/fetch` | ✅ **Resolved** (Hardened in Phase 2 via SEC-16 & SEC-17: hex IPv4-mapped IPv6 blocked, HTML payload denied, streaming 2MB cap, sandboxed XML header) |
| **SEC-04** | 🟠 **High** | Host Header Injection & Web Cache Poisoning in `/api/share` | ✅ **Resolved** (Hardened in Phase 2 via SEC-18: exact regex host matching, function replacer prevents `$` injection) |
| **SEC-05** | 🟡 **Medium** | DOM-Based XSS via Unescaped Story & Section Metadata | ✅ **Resolved** (`escapeHtml()` applied in `renderAllStoriesSheet`) |
| **SEC-06** | 🟡 **Medium** | Android WebView Remote Debugging Enabled in Production | ✅ **Resolved** (Gated behind `ApplicationInfo.FLAG_DEBUGGABLE`) |
| **SEC-07** | 🟡 **Medium** | Android Mixed Content & Unvalidated Intent URL Scheme | ✅ **Resolved** (`allowMixedContent: false`, HTTPS scheme enforced in `openExternalAuth`) |
| **SEC-08** | 🟡 **Medium** | iOS App Transport Security Globally Disabled | ✅ **Resolved** (`NSAllowsArbitraryLoads = false`, `NSAllowsLocalNetworking = true`) |
| **SEC-09** | 🟡 **Medium** | Unauthenticated Anonymous Insert Spam on `public.content_reports` | ✅ **Resolved** (Column length constraints enforced in RLS `with check`) |
| **SEC-10** | 🟡 **Medium** | Unvalidated `model` Parameter Interpolated into Google API URL | ✅ **Resolved** (`/^[a-zA-Z0-9._-]+$/` regex enforced in `llm.js` and `tts.js`) |
| **SEC-11** | 🟡 **Medium** | Unauthenticated Voice Service API with Unbounded Input | ✅ **Resolved** (`max_length=10000`, `VOICE_API_KEY` dependency, restricted CORS) |
| **SEC-12** | 🟢 **Low** | Plaintext Android Release Keystore Password on Disk | ✅ **Resolved** (Excluded via `.gitignore`, `0600` file permissions) |
| **SEC-13** | 🟢 **Low** | Internal Network Topology & Personal Email Hardcoded in Repo | ✅ **Resolved** (Hardened in Phase 2 via DATA-02: hardcoded emails removed from `web/js/api.js` & `supabase/schema.sql`) |
| **SEC-14** | 🟢 **Low** | Unescaped String Interpolation in macOS `osascript` Command | ✅ **Resolved** (Backslashes and double quotes escaped before `osascript`) |

---

## 2. Phase 2: New Security Risks (`SEC-15` – `SEC-24`)

| ID | Severity | Vulnerability | Component / Location | Status |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-15** | 🔴 **Critical** | Authentication Bypass in `/api/feedback` via Boolean Logic Flaw (`!verifiedUser && !token`) | [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L124) | ✅ **Resolved** (Unconditionally enforces `verifiedUser`) |
| **SEC-16** | 🔴 **Critical** | Same-Origin Reflected XSS & Session Token Theft via Upstream `Content-Type` Echo in `/api/fetch` | [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L152-L153) | ✅ **Resolved** (HTML payloads rejected, safe sandboxed XML headers) |
| **SEC-17** | 🟠 **High** | SSRF Bypass via DNS Rebinding (TOCTOU), Hex IPv6-Mapped IPv4 (`::ffff:7f00:1`), and Pre-Limit Memory Buffering | [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L19-L59) | ✅ **Resolved** (Hex mapped IPv4 parsed, pre-check & streaming size abort) |
| **SEC-18** | 🟠 **High** | Web Cache Poisoning via `localhost.evil.com` / `*.vercel.app` Host Prefix & `$` Replacement Pattern Injection in `/api/share` | [`web/api/share.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/share.js#L152-L229) | ✅ **Resolved** (Exact host regex, replacer function prevents pattern expansion) |
| **SEC-19** | 🟡 **Medium** | `javascript:` / `data:` URI XSS in Story External Article Links (`story.url`) | [`web/js/player.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/player.js#L1170), [`web/js/app.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/app.js#L1066), [`app/fetcher.py`](file:///Users/vattitude/Coding/Morning_Brief/app/fetcher.py#L192) | ✅ **Resolved** (`safeExternalUrl()` validator across all links and fetcher) |
| **SEC-20** | 🟡 **Medium** | Android `evaluateJavascript` String Injection via Unescaped Newlines (`\n`, `\r`, `\u2028`, `\u2029`) in Deep Link Intents | [`MainActivity.java`](file:///Users/vattitude/Coding/Morning_Brief/android/app/src/main/java/me/vattitude/morningbrief/MainActivity.java#L83-L120) | ✅ **Resolved** (`JSONObject.quote()` used across all evaluateJavascript calls) |
| **SEC-21** | 🟡 **Medium** | Mutable `search_path = public` & Missing `REVOKE FROM PUBLIC` on `SECURITY DEFINER` Function `delete_user_account()` | [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L391-L403) | ✅ **Resolved** (`search_path = ''`, revoked from public & anon) |
| **SEC-22** | 🟡 **Medium** | Unthrottled `build_requests` Queue Flooding (`push_test`) & Missing `payload` Column Grant | [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L224-L253) | ✅ **Resolved** (Max 3 pending requests per user, payload column granted) |
| **SEC-23** | 🟡 **Medium** | Missing Content-Security-Policy (CSP), `X-Frame-Options`, and HSTS Headers | [`web/vercel.json`](file:///Users/vattitude/Coding/Morning_Brief/web/vercel.json#L6-L13) | ✅ **Resolved** (Frame-ancestors 'none', X-Frame-Options DENY, HSTS, Permissions-Policy) |
| **SEC-24** | 🟢 **Low** | Ephemeral In-Memory Rate Limiting & Spoofable `X-Forwarded-For` Header in `/api/feedback` | [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L14-L35) | ✅ **Resolved** (Authoritative `x-real-ip`, restricted Vercel origins) |

---

### Detailed Security Risk Analysis & Fixes

#### SEC-15 (Critical): Authentication Bypass in `/api/feedback` via Boolean Logic Flaw
- **Location:** [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L124)
- **Root Cause:**
  Line 124 checks:
  ```javascript
  if (!verifiedUser && !token && !isTestEnv) {
    return res.status(401).json({ error: 'Authentication required. Please sign in to submit feedback.' });
  }
  ```
  If an unauthenticated spammer sends `Authorization: Bearer fake-invalid-token`, `token` is non-empty (`!token` is `false`), while Supabase rejects the token so `verifiedUser` is `null`. Because the condition uses `&& !token`, **`!verifiedUser && !token` evaluates to `false`**, and the request proceeds right past the auth check and posts to your Discord webhook!
- **Remediation:**
  Change line 124 to require `verifiedUser` unconditionally outside tests:
  ```javascript
  if (!verifiedUser && !isTestEnv) {
    return res.status(401).json({ error: 'Authentication required. Please sign in to submit feedback.' });
  }
  ```

---

#### SEC-16 (Critical): Same-Origin Reflected XSS & Session Token Theft via `/api/fetch`
- **Location:** [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L151-L153)
- **Root Cause:**
  ```javascript
  res.setHeader('Cache-Control', 'public, max-age=300');
  res.setHeader('Content-Type', upstream.headers.get('content-type') || 'application/xml');
  return res.status(upstream.status).send(text);
  ```
  `/api/fetch` mirrors the upstream server's `Content-Type` header (`text/html`, `image/svg+xml`, etc.) directly onto the `https://hark.vattitude.ca` origin. If an attacker tricks a user into visiting `https://hark.vattitude.ca/api/fetch?url=https://attacker.example/payload.html`, the browser renders the attacker's HTML/JavaScript **under the `https://hark.vattitude.ca` origin**, giving the script full read/write access to `localStorage` (stealing the user's Supabase JWT `access_token` and `refresh_token`).
- **Remediation:**
  1. Never echo `text/html` or `image/svg+xml` from `/api/fetch`. Force a safe non-executable content type:
     ```javascript
     res.setHeader('Content-Type', 'application/xml; charset=utf-8');
     res.setHeader('X-Content-Type-Options', 'nosniff');
     res.setHeader('Content-Security-Policy', "default-src 'none'; sandbox");
     ```
  2. Reject upstream responses whose `Content-Type` is `text/html` if `/api/fetch` is only intended for RSS/Atom XML feeds.

---

#### SEC-17 (High): SSRF Bypass via DNS Rebinding (TOCTOU), Hex IPv6-Mapped IPv4, and Unbounded ArrayBuffer Allocation
- **Location:** [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L19-L59) and [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L117-L148)
- **Root Cause:**
  1. **Hex IPv6-Mapped IPv4 Bypass:** When `new URL('http://[::ffff:127.0.0.1]/')` or `new URL('http://[::ffff:169.254.169.254]/')` is parsed by Node, `parsed.hostname` is normalized to `'[::ffff:7f00:1]'` (hexadecimal notation, not dotted quad). In `isPrivateOrReservedIP(ipStr)`, `cleanIp` becomes `'7f00:1'`, `isIP('7f00:1')` returns `0`, and if passed as full IPv6 `'::ffff:7f00:1'`, `isIP` returns `6` where lines 50–58 only check `::1`, `fe80::/10`, and `fc00::/7` — returning `false` (allowed)!
  2. **DNS Rebinding (TOCTOU):** `dns.lookup(parsed.hostname)` resolves the domain once at line 117, and `fetch(parsed.href)` performs a second independent DNS lookup at line 131. An attacker using a TTL=0 DNS rebinding responder can return a public IP on lookup #1 and `169.254.169.254` or `127.0.0.1` on lookup #2.
  3. **Memory Exhaustion Before Size Check:** Line 145 calls `const arrayBuffer = await upstream.arrayBuffer();` *before* checking `arrayBuffer.byteLength > MAX_BYTES`. A multi-hundred-megabyte upstream stream is buffered entirely into memory before line 146 runs.
- **Remediation:**
  1. Block all `::ffff:` (IPv4-mapped IPv6), `64:ff9b::` (NAT64), `2001:db8::` (documentation), and `100::` addresses in the IPv6 branch (`if (lower.startsWith('::ffff:')) return true;`).
  2. Stream the response body with a byte counter (`for await (const chunk of upstream.body)`) and abort immediately when total bytes exceed `MAX_BYTES`.

---

#### SEC-18 (High): Web Cache Poisoning via `localhost.evil.com` / `*.vercel.app` & `$` Replacement Pattern Injection in `/api/share`
- **Location:** [`web/api/share.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/share.js#L151-L156) and [`web/api/share.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/share.js#L198-L229)
- **Root Cause:**
  1. **Host Prefix/Suffix Bypass:**
     ```javascript
     if (reqHost.endsWith('.vercel.app')) {
       origin = `https://${reqHost}`;
     } else if (reqHost.startsWith('localhost') || reqHost.startsWith('127.0.0.1')) {
       origin = `http://${reqHost}`;
     }
     ```
     - `reqHost.startsWith('localhost')` matches `localhost.attacker.com`!
     - `reqHost.endsWith('.vercel.app')` matches *any* attacker's Vercel project (`attacker-phishing.vercel.app`)!
     - Because line 232 sets `Cache-Control: public, s-maxage=300, stale-while-revalidate=86400`, sending a request with `X-Forwarded-Host: localhost.attacker.com` poisons the shared CDN cache for 24 hours so every visitor's OpenGraph URL, canonical link, and fallback thumbnail point to `http://localhost.attacker.com`.
  2. **`String.prototype.replace` Special `$` Pattern Injection:**
     Lines 199–213 and 229 pass dynamic strings (`eTitle`, `eDesc`, `safeJson`) as the second argument to `.replace(pattern, replacement)`. In JavaScript, `$&`, `` $` ``, and `$'` in the replacement string expand to the matched or surrounding HTML document! If a news headline or transcript contains `"$`"` or `"$'"` (e.g., currency/ticker text), `.replace('</head>', ...)` splices raw unescaped portions of `index.html` inside the `<script>` tag.
- **Remediation:**
  1. Strictly validate `reqHost` against `/^localhost(:\d+)?$/` or your specific Vercel deployment prefix, or always use `CANONICAL_ORIGIN` when caching publicly (`s-maxage`).
  2. Pass a function `() => replacement` as the second argument to `.replace(...)` on lines 199–213 and 229 so `$` patterns are never interpreted.

---

#### SEC-19 (Medium): `javascript:` / `data:` URI XSS in Story External Article Links (`story.url`)
- **Location:** [`web/js/player.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/player.js#L1170), [`web/js/player.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/player.js#L1223), [`web/js/player.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/player.js#L1584), [`web/js/app.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/app.js#L1066), [`app/fetcher.py`](file:///Users/vattitude/Coding/Morning_Brief/app/fetcher.py#L192), and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L280)
- **Root Cause:**
  - `public.story_audio.url` in [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L280) checks `char_length(url) <= 2000` but does not enforce `url ~* '^https?://'`.
  - `parse_feed()` in [`app/fetcher.py`](file:///Users/vattitude/Coding/Morning_Brief/app/fetcher.py#L192) accepts `link = entry.get("link")` without checking that its scheme is `http` or `https`.
  - In the frontend (`player.js` and `app.js`), `heroArticle.href = story.url` and `readerArticleLink.href = story.url` assign `story.url` directly without verifying `/^https?:\/\//i.test(story.url)`.
- **Remediation:**
  Enforce `/^https?:\/\//i.test(url)` in both `app/fetcher.py` (`parse_feed`) and a helper `safeExternalUrl(url)` in `web/js/player.js` / `web/js/app.js`.

---

#### SEC-20 (Medium): Android `evaluateJavascript` Injection via Unescaped Newlines / Line Separators in Deep Link Intents
- **Location:** [`android/app/src/main/java/me/vattitude/morningbrief/MainActivity.java`](file:///Users/vattitude/Coding/Morning_Brief/android/app/src/main/java/me/vattitude/morningbrief/MainActivity.java#L83-L120)
- **Root Cause:**
  In `handleAuthIntent`, `handleDeepLinkIntent`, and `dispatchNativeAuthError`:
  ```java
  String safeUri = fullUri.replace("\\", "\\\\").replace("'", "\\'");
  webView.evaluateJavascript(
      "window.handleDeepLinkUrl && window.handleDeepLinkUrl('" + safeUri + "');",
      null
  );
  ```
  Single-quoted JavaScript string literals cannot contain unescaped `\n`, `\r`, `\u2028`, or `\u2029`. An external app or browser invoking the exported deep-link intent `me.vattitude.morningbrief://auth?...` with encoded line separators or control characters can break out of the JS string literal.
- **Remediation:**
  Use `org.json.JSONObject.quote(fullUri)` (which produces a properly escaped JSON string literal including surrounding double quotes) instead of manual `.replace(...)`.

---

#### SEC-21 (Medium): Mutable `search_path = public` & Missing `REVOKE FROM PUBLIC` on `SECURITY DEFINER` Function
- **Location:** [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L391-L403)
- **Root Cause:**
  ```sql
  create or replace function public.delete_user_account()
  returns void
  language plpgsql
  security definer
  set search_path = public
  ...
  revoke all on function public.delete_user_account() from anon;
  ```
  1. Unlike `handle_new_user()` and `is_admin()` (which use `set search_path = ''`), `delete_user_account()` sets `search_path = public` while running with `SECURITY DEFINER` (superuser/owner privileges).
  2. In PostgreSQL, new functions grant `EXECUTE` to the `PUBLIC` pseudo-role by default. Revoking from `anon` without `revoke all on function public.delete_user_account() from public;` leaves default `PUBLIC` execute permissions intact.
- **Remediation:**
  Set `set search_path = ''` and run `revoke all on function public.delete_user_account() from public, anon;`.

---

#### SEC-22 (Medium): Unthrottled `build_requests` Queue Flooding & Missing `payload` Grant
- **Location:** [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L224-L253)
- **Root Cause:**
  1. Policy `"create requests"` allows any `authenticated` user to insert unlimited rows with `kind in ('push_test', 'delete_account')` and `status = 'queued'`. Unlike `public.sources` (which caps rows at `< 25`), there is no per-user limit on pending `build_requests`. A malicious user can insert thousands of `push_test` jobs in seconds, starving the background worker and triggering outbound Web Push floods.
  2. Line 253 (`grant insert (user_id, kind) on public.build_requests to authenticated;`) omits the `payload` column, preventing admin `pack` requests from passing rebuild options via `payload`.
- **Remediation:**
  1. Add a check to `"create requests"` limiting each user to at most 3 pending (`status in ('queued', 'running')`) requests at a time.
  2. Update line 253 to `grant insert (user_id, kind, payload) on public.build_requests to authenticated;` with a size check `check (payload is null or pg_column_size(payload) <= 2048)`.

---

#### SEC-23 (Medium): Missing Content-Security-Policy (CSP), `X-Frame-Options`, and HSTS Headers
- **Location:** [`web/vercel.json`](file:///Users/vattitude/Coding/Morning_Brief/web/vercel.json#L6-L13)
- **Root Cause:**
  [`web/vercel.json`](file:///Users/vattitude/Coding/Morning_Brief/web/vercel.json) only sets `X-Content-Type-Options: nosniff` and `Referrer-Policy`. It lacks:
  - `X-Frame-Options: DENY` / `CSP frame-ancestors 'none'` (leaves the web app vulnerable to Clickjacking / UI redressing inside an attacker's `<iframe>`).
  - `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- **Remediation:**
  Add `X-Frame-Options: DENY`, `Strict-Transport-Security`, `Permissions-Policy`, and a `Content-Security-Policy` header to [`web/vercel.json`](file:///Users/vattitude/Coding/Morning_Brief/web/vercel.json).

---

#### SEC-24 (Low): Ephemeral In-Memory Rate Limiting & Spoofable `X-Forwarded-For` in `/api/feedback`
- **Location:** [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L14-L35) and [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L129)
- **Root Cause:**
  1. `headers['x-forwarded-for']?.split(',')[0]?.trim()` reads the leftmost IP in `X-Forwarded-For`, which can be spoofed by clients if an upstream proxy appends rather than overwrites. On Vercel, `x-real-ip` or the rightmost hop set by Vercel Edge is authoritative.
  2. `origin.endsWith('.vercel.app')` on line 35 allows any third-party Vercel site to make cross-origin requests to `/api/feedback`.

---

## 3. Data & Privacy Risks (`DATA-01` – `DATA-07`)

Beyond code execution and network vulnerabilities, we audited how user data, PII, credentials, and storage objects flow across the system:

| ID | Severity | Data / Privacy Risk | Component / Location | Status |
| :--- | :--- | :--- | :--- | :--- |
| **DATA-01** | 🟠 **High** | Admin Email & Internal Run Diagnostics Broadcast to All Signed-In Users via `public.app_status` | [`app/worker.py`](file:///Users/vattitude/Coding/Morning_Brief/app/worker.py#L87-L91), [`app/worker.py`](file:///Users/vattitude/Coding/Morning_Brief/app/worker.py#L202-L228), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L239) | ✅ **Resolved** (Sanitized `by: "admin"`, error traces isolated to admin run log) |
| **DATA-02** | 🟡 **Medium** | Undisclosed Visitor IP Address Leakage to Third-Party Service (`api.country.is`) & Hardcoded Admin Email in Client Bundle | [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L127), [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L247) | ✅ **Resolved** (External IP API removed, hardcoded emails removed) |
| **DATA-03** | 🟡 **Medium** | Incomplete Account Deletion (Orphaned User Audio Files in Public Storage Bucket When Using `delete_user_account()` RPC) | [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L686-L690), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L391-L400) | ✅ **Resolved** (RPC cleans up user storage bucket objects on deletion) |
| **DATA-04** | 🟡 **Medium** | Unbounded JSONB Storage Growth in `public.profiles.settings` (Database Storage Exhaustion) | [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L17), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L247) | ✅ **Resolved** (`check (pg_column_size(settings) <= 16384)` constraint added) |
| **DATA-05** | 🟡 **Medium** | Android `android:allowBackup="true"` Permits Extraction of WebView `localStorage` Session Tokens | [`AndroidManifest.xml`](file:///Users/vattitude/Coding/Morning_Brief/android/app/src/main/AndroidManifest.xml#L12) | ✅ **Resolved** (`android:allowBackup="false"` enforced) |
| **DATA-06** | 🟡 **Medium** | Unbounded `push_subscriptions` Rows & Unconstrained `p256dh`/`auth` Column Sizes | [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L105-L111) | ✅ **Resolved** (Strict HTTPS, key length caps, and `< 10` per user quota) |
| **DATA-07** | 🟢 **Low** | Indefinite Retention of User PII & Error Stacks in `content_reports` and `localStorage` (`mb-diagnostics-log`) | [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L160-L172), [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L287-L303) | ✅ **Resolved** (Diagnostics log purged on `signOut`) |

---

### Detailed Data & Privacy Risk Analysis

#### DATA-01 (High): Admin Email & Internal Run Diagnostics Exposed to All Users via `public.app_status`
- **Location:** [`app/worker.py`](file:///Users/vattitude/Coding/Morning_Brief/app/worker.py#L87-L91), [`app/worker.py`](file:///Users/vattitude/Coding/Morning_Brief/app/worker.py#L205-L228), and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L239)
- **Risk:**
  `public.app_status` has RLS policy `for select to authenticated using (true)`. However, `Worker.run_pack()` and `Worker.run_batch()` write sensitive operational metadata directly into `app_status.data`:
  - `"by": (profile or {}).get("email")` (exposes the admin's personal email address to every signed-in user).
  - `"error": f"{exc.__class__.__name__}: {exc}"[:300]` and `last_run: report.to_dict()` (exposes internal Python exception messages, stack failure summaries, and upstream errors).
- **Remediation:**
  Omit `"by"` (or store a boolean `"triggered_by_admin": True`) and sanitize `"error"` in `app_status.data`, keeping detailed error traces strictly inside `public.run_log` (which is already protected by `using (public.is_admin())`).

---

#### DATA-02 (Medium): Undisclosed Visitor IP Leakage to Third-Party (`api.country.is`) & Hardcoded Admin Email in Client JS
- **Location:** [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L127) and [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L247)
- **Risk:**
  1. When `detectEditionFromIp()` runs and `/api/geo` is unreachable or returns no country header (such as on mobile WebViews or local networks), line 127 automatically calls `fetch('https://api.country.is/')` from the user's browser, transmitting the user's IP address and browser headers to an external third-party service not listed in [`web/privacy.html`](file:///Users/vattitude/Coding/Morning_Brief/web/privacy.html).
  2. Line 247 hardcodes `export const ADMIN_EMAILS = ['vatsakrish@gmail.com'];` directly in the client bundle [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L247) (and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L220)). Because `profile.is_admin` is already stored in Supabase `public.profiles`, the client only needs to check `profile?.is_admin === true`.
- **Remediation:**
  1. Fall back to `defaultEdition()` (locale/timezone detection) instead of calling external `https://api.country.is/` when `/api/geo` returns no country.
  2. Remove the hardcoded email from `ADMIN_EMAILS` in [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L247) and rely on `profile?.is_admin === true`.

---

#### DATA-03 (Medium): Incomplete Account Deletion Leaves Orphaned User Files in Public Storage Bucket
- **Location:** [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L686-L690) and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L391-L400)
- **Risk:**
  In `api.deleteAccount()`, step 1 calls `await sb.rpc('delete_user_account')` and immediately returns if it succeeds (`if (!error) return;`). Because `delete_user_account()` deletes the row in `auth.users` directly inside PostgreSQL, step 3 (`api.request('delete_account')`, which tells the Python worker to delete `/<feed_token>/*.mp3` from the public `briefings` bucket via `Worker.delete_account()`) is **never reached**. Any legacy per-user audio files under `<feed_token>/` remain orphaned in the public bucket indefinitely.
- **Remediation:**
  Have `delete_user_account()` also delete any matching objects in `storage.objects` where `bucket_id = 'briefings'` and the path starts with the user's `feed_token` before deleting from `auth.users`.

---

#### DATA-04 (Medium): Unbounded JSONB Storage Growth in `public.profiles.settings`
- **Location:** [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L17) and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L247)
- **Risk:**
  Authenticated users have `grant update (settings) on public.profiles to authenticated;`, and there is no `CHECK` constraint limiting the byte size of `settings`. A single authenticated user can `PATCH /rest/v1/profiles` with a 50 MB JSON object in `settings`, bloating the database and slowing down `self.store.profiles()` in the Python worker (which loads all profiles into memory every 10 seconds in `poll_requests()`!).
- **Remediation:**
  Add a constraint on `public.profiles`:
  ```sql
  alter table public.profiles add constraint profiles_settings_size_check
    check (pg_column_size(settings) <= 16384);
  ```

---

#### DATA-05 (Medium): Android `android:allowBackup="true"` Exposes WebView Session Storage
- **Location:** [`android/app/src/main/AndroidManifest.xml`](file:///Users/vattitude/Coding/Morning_Brief/android/app/src/main/AndroidManifest.xml#L12)
- **Risk:**
  `android:allowBackup="true"` is enabled without `android:fullBackupContent` or `android:dataExtractionRules` excluding WebView storage. Because Supabase stores the user's active JWT and long-lived refresh token in WebView `localStorage`, device backups can extract live authentication tokens.
- **Remediation:**
  Set `android:allowBackup="false"` in [`AndroidManifest.xml`](file:///Users/vattitude/Coding/Morning_Brief/android/app/src/main/AndroidManifest.xml#L12) (since all user settings and sources are already synced to Supabase or easily re-created).

---

#### DATA-06 (Medium): Unbounded `push_subscriptions` Rows & Unconstrained `p256dh`/`auth` Sizes
- **Location:** [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L105-L111) and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L209-L211)
- **Risk:**
  `public.push_subscriptions` does not constrain `char_length(p256dh)` or `char_length(auth)`, does not enforce `endpoint ~* '^https://'` in SQL, and does not cap the number of subscriptions per user (e.g., max 10 devices per user).
- **Remediation:**
  Add `check (endpoint ~* '^https://' and char_length(p256dh) <= 512 and char_length(auth) <= 256)` and limit inserts to `< 10` rows per `user_id` in the RLS policy.

---

#### DATA-07 (Low): Indefinite Retention of Error Stack Traces in `localStorage` & Reports in Supabase
- **Location:** [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L287-L303) and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L160-L172)
- **Risk:**
  1. `recordError()` stores up to 50 raw error messages and stack traces in `localStorage` (`mb-diagnostics-log`) and does not clear them on `api.signOut()`, which on a shared browser can leave diagnostic traces from a previous session.
  2. `public.content_reports` retains `user_id` and report rows indefinitely with no automated cleanup/TTL policy.
- **Remediation:**
  Clear `mb-diagnostics-log` inside `api.signOut()` and periodically prune `content_reports` older than 90 days.

---

## 4. Phase 3 Fresh Audit: Security, Architectural & Data Risks (Post-Commit `b368cfb`)

Following commit `b368cfb` (#53), we verified all 17 Phase 2 fixes (`SEC-15`–`SEC-24` and `DATA-01`–`DATA-07`) and performed a fresh end-to-end audit across the backend worker, serverless APIs, database schema, Service Worker, and CI/CD pipelines.

### 4.1 Phase 3 Security Risks (`SEC-25` – `SEC-31`)

| ID | Severity | Vulnerability | Component / Location | Status |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-25** | 🟠 **High** | Blind `POST` SSRF (Internal Home LAN Access) & VAPID JWT Leakage via Unconstrained `push_subscriptions.endpoint` Host | [`app/push.py`](file:///Users/vattitude/Coding/Morning_Brief/app/push.py#L48-L55), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L106) | ⚠️ **Open** |
| **SEC-26** | 🟠 **High** | Dead Legacy BYOK Proxy Endpoints (`/api/llm`, `/api/tts`, `/api/fetch`) Exposed in Production Without Auth or Rate Limiting | [`web/api/llm.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/llm.js#L35-L41), [`web/api/tts.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/tts.js#L35-L41), [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L89) | ⚠️ **Open** |
| **SEC-27** | 🟠 **High** | Permissive Vercel Subdomain Regex (`(hark\|morning-brief)[a-z0-9-]*\.vercel\.app`) Allows Third-Party Vercel Cache Poisoning & CORS Bypass | [`web/api/share.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/share.js#L153), [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L38), [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L99) | ⚠️ **Open** |
| **SEC-28** | 🟡 **Medium** | Pre-Authentication Supabase Auth Request Amplification in `/api/feedback` (Rate Limit Checked *After* Outbound Auth Call) | [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L111-L136) | ⚠️ **Open** |
| **SEC-29** | 🟡 **Medium** | Service Worker Intercepts & Caches `/api/*` GET Endpoints, Returns HTML Shell on API Failure, and Trusts Unvalidated Notification URLs | [`web/sw.js`](file:///Users/vattitude/Coding/Morning_Brief/web/sw.js#L27-L68), [`web/sw.js`](file:///Users/vattitude/Coding/Morning_Brief/web/sw.js#L90-L98) | ⚠️ **Open** |
| **SEC-30** | 🟡 **Medium** | Dead `api.uploadVoiceFile` Helper Interpolates Unsanitized `voiceId` Into Storage Path (`voices/${voiceId}.wav`) | [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L643-L654) | ⚠️ **Open** |
| **SEC-31** | 🟢 **Low** | Over-Privileged GitHub Actions `contents: write` Token on Non-Release Runs, Unvalidated Tag Arithmetic, & Missing JS Security Tests in CI | [`.github/workflows/android.yml`](file:///Users/vattitude/Coding/Morning_Brief/.github/workflows/android.yml#L14-L55), [`.github/workflows/tests.yml`](file:///Users/vattitude/Coding/Morning_Brief/.github/workflows/tests.yml#L1-L26) | ⚠️ **Open** |

---

### 4.2 Phase 3 Data, Migration & Privacy Risks (`DATA-08` – `DATA-10`)

| ID | Severity | Data / Infrastructure Risk | Component / Location | Status |
| :--- | :--- | :--- | :--- | :--- |
| **DATA-08** | 🟠 **High** | Inline `CREATE TABLE IF NOT EXISTS` Constraints Added in Commit `b368cfb` Are Skipped on Existing Production Tables | [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L17), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L106-L109), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L125), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L290) | ⚠️ **Open** |
| **DATA-09** | 🟡 **Medium** | Direct SQL `DELETE FROM storage.objects` in `delete_user_account()` Can Abort Account Deletion Due to Supabase Storage Trigger | [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L418) | ⚠️ **Open** |
| **DATA-10** | 🟢 **Low** | Hardcoded Admin Email Remaining in `web/js/pages/admin.js` & Unsanitized `last_run` Report Published to `public.app_status` | [`web/js/pages/admin.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/pages/admin.js#L216-L231), [`app/worker.py`](file:///Users/vattitude/Coding/Morning_Brief/app/worker.py#L87-L91) | ⚠️ **Open** |

---

### 4.3 Detailed Phase 3 Findings & Remediations

#### SEC-25 (High): Blind `POST` SSRF (Internal Home LAN Access) & VAPID JWT Leakage via `push_subscriptions.endpoint`
- **Location:** [`app/push.py`](file:///Users/vattitude/Coding/Morning_Brief/app/push.py#L48-L55) and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L106)
- **Root Cause:**
  1. In [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L106), `push_subscriptions.endpoint` only checks `endpoint ~* '^https://'`. Any authenticated user can insert a row into `public.push_subscriptions` with an arbitrary `endpoint` (e.g., `https://attacker.example/hook` or an internal HTTPS service on the Mac worker's local network such as `https://10.0.0.233:5001/api/...`) and then queue a `push_test` request (`api.pushTest()`).
  2. Within 10 seconds, `Worker.poll_requests()` running on the primary Mac inside the home LAN calls `webpush(subscription_info={"endpoint": sub["endpoint"], ...})` ([`app/push.py`](file:///Users/vattitude/Coding/Morning_Brief/app/push.py#L48-L55)) without calling `check_public_url()` or verifying that the hostname belongs to a legitimate browser push service.
  3. In addition to blind `POST` SSRF from inside the home network, `pywebpush` sends a signed VAPID `Authorization` JWT (`vapid_claims={"sub": self.subject, "aud": origin}`) and your public VAPID key directly to the attacker's server.
- **Remediation:**
  Enforce an allowlist of official Web Push service domains in both [`app/push.py`](file:///Users/vattitude/Coding/Morning_Brief/app/push.py) (alongside `check_public_url()`) and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql):
  - `*.push.services.mozilla.com` / `*.mozaws.net` (Firefox)
  - `fcm.googleapis.com` / `*.google.com` / `*.googleapis.com` (Chrome / Android / Edge)
  - `*.push.apple.com` (Safari / iOS / macOS)
  - `*.notify.windows.com` (WNS)

---

#### SEC-26 (High): Dead Legacy BYOK Proxy Endpoints (`/api/llm`, `/api/tts`, `/api/fetch`) Exposed in Production
- **Location:** [`web/api/llm.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/llm.js), [`web/api/tts.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/tts.js), and [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js)
- **Root Cause:**
  As documented in [`web/js/pages/settings.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/pages/settings.js#L3) (*"The BYOK voice list and the AI-key panel went with the builder they served"*), the client-side BYOK pack builder was removed from the web app, and zero production files in `web/` invoke `/api/llm`, `/api/tts`, or `/api/fetch`. However, all three serverless endpoints remain live on Vercel (`https://hark.vattitude.ca/api/llm`, `/api/tts`, `/api/fetch`):
  1. `/api/llm` and `/api/tts` have **no authentication, no CORS origin check, no rate limiting, and no request body size cap**, allowing anyone on the internet to use `hark.vattitude.ca` as a free anonymizing proxy for Groq, OpenRouter, and Gemini API calls while consuming your Vercel serverless function execution time and bandwidth quota.
  2. `/api/fetch` remains an unauthenticated public XML proxy that is still susceptible to DNS rebinding (TOCTOU between `dns.lookup()` at line 150 and `fetch()` at line 164).
- **Remediation:**
  Remove `/api/llm.js`, `/api/tts.js`, and `/api/fetch.js` from the public Vercel deployment (or disable them with `410 Gone` / require a verified admin Supabase JWT if kept for internal testing).

---

#### SEC-27 (High): Permissive Vercel Subdomain Regex Allows Third-Party Vercel Cache Poisoning & CORS Bypass
- **Location:** [`web/api/share.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/share.js#L153), [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L38), and [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L99)
- **Root Cause:**
  Commit `b368cfb` tightened `.endsWith('.vercel.app')` to:
  ```javascript
  const isHarkVercel = /^(hark|morning-brief)[a-z0-9-]*\.vercel\.app$/i.test(reqHost);
  ```
  However, `.vercel.app` is a public shared domain where any Vercel user worldwide can register a project named `hark-phishing` (`https://hark-phishing.vercel.app`) or `morning-brief-evil.vercel.app`.
  1. In [`web/api/share.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/share.js#L153-L234), sending `GET https://hark.vattitude.ca/s/<id>` with header `X-Forwarded-Host: hark-phishing.vercel.app` satisfies `isHarkVercel`, sets `origin = "https://hark-phishing.vercel.app"`, and caches that poisoned HTML (`og:url`, `<link rel="canonical">`, `og:image`) across the Vercel CDN for all subsequent users (`Cache-Control: public, s-maxage=300, stale-while-revalidate=86400`).
  2. In [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L38) and [`web/api/fetch.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/fetch.js#L99), `https://hark-phishing.vercel.app` is granted cross-origin `Access-Control-Allow-Origin` access.
- **Remediation:**
  1. In [`web/api/share.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/share.js), always use `CANONICAL_ORIGIN` (`https://hark.vattitude.ca`) unless `reqHost` matches `/^(localhost|127\.0\.0\.1)(:\d+)?$/` or equals `process.env.VERCEL_URL` (and when serving non-canonical origins, set `Vary: Host, X-Forwarded-Host` or `Cache-Control: private, no-store`).
  2. In `feedback.js` and `fetch.js`, only allow `https://${process.env.VERCEL_URL}` and `https://${process.env.VERCEL_BRANCH_URL}` (plus `https://hark.vattitude.ca`) instead of wildcard `[a-z0-9-]*\.vercel\.app`.

---

#### DATA-08 (High): Inline `CREATE TABLE IF NOT EXISTS` Constraints Are Skipped on Existing Production Tables
- **Location:** [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L17), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L106-L109), [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L125), and [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L290)
- **Root Cause:**
  Commit `b368cfb` added four `CHECK` constraints inline inside `create table if not exists` blocks:
  - `public.profiles`: `check (pg_column_size(settings) <= 16384)` (`DATA-04`)
  - `public.push_subscriptions`: `check (endpoint ~* '^https://' ...)`, `p256dh <= 512`, `auth <= 256` (`DATA-06`)
  - `public.build_requests`: `check (payload is null or pg_column_size(payload) <= 2048)` (`SEC-22`)
  - `public.story_audio`: `check (url is null or (char_length(url) <= 2000 and url ~* '^https?://'))` (`SEC-19`)
  In PostgreSQL, when `CREATE TABLE IF NOT EXISTS` runs against a database where the table already exists, the entire statement is a no-op — **none of the new inline `CHECK` constraints are added to your existing Supabase production tables**.
- **Remediation:**
  Add explicit idempotent `ALTER TABLE ... DROP CONSTRAINT IF EXISTS ...; ALTER TABLE ... ADD CONSTRAINT ... NOT VALID; ALTER TABLE ... VALIDATE CONSTRAINT ...;` migration statements to [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql).

---

#### DATA-09 (Medium): Direct SQL `DELETE FROM storage.objects` in `delete_user_account()` Can Fail Under Supabase Storage Trigger
- **Location:** [`supabase/schema.sql`](file:///Users/vattitude/Coding/Morning_Brief/supabase/schema.sql#L416-L420)
- **Root Cause:**
  Commit `b368cfb` added:
  ```sql
  if u_token is not null and char_length(u_token) > 0 then
    delete from storage.objects
    where bucket_id = 'briefings' and name like (u_token || '/%');
  end if;
  ```
  Supabase Storage installs a protective trigger (`storage.protect_delete()`) on `storage.objects` in hosted Supabase projects that raises `ERROR: Direct deletion from storage tables is not allowed. Use the Storage API instead.` Unless bypassed or caught, this exception aborts the entire `delete_user_account()` transaction and prevents `delete from auth.users where id = uid;` from executing. Furthermore, `u_token` should escape `_` and `%` if used with `LIKE`, or use `left(name, char_length(u_token) + 1) = (u_token || '/')`.
- **Remediation:**
  Wrap the `storage.objects` delete in a `begin ... exception when others then null; end;` block inside `delete_user_account()` and use exact prefix comparison (`starts_with(name, u_token || '/')`), while also allowing the client/worker Storage API cleanup to run before invoking the RPC.

---

#### SEC-28 (Medium): Pre-Authentication Supabase Auth Request Amplification in `/api/feedback`
- **Location:** [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js#L111-L136)
- **Root Cause:**
  In [`web/api/feedback.js`](file:///Users/vattitude/Coding/Morning_Brief/web/api/feedback.js), `isRateLimited('ip:' + ip)` is checked at line 135 — **after** performing an outbound HTTP call `await fetch("${SUPABASE_URL}/auth/v1/user")` at line 113 and returning `401` at line 129.
  An attacker sending floods of requests with random invalid Bearer tokens (`Authorization: Bearer invalid-123`) returns at line 129 before `isRateLimited('ip:' + ip)` is ever recorded, amplifying traffic against your Supabase Auth instance and Vercel function duration.
- **Remediation:**
  Check `isRateLimited('ip:' + ip)` **before** making the outbound `fetch("${SUPABASE_URL}/auth/v1/user")` call.

---

#### SEC-29 (Medium): Service Worker Intercepts `/api/*` GET Endpoints, Falls Back to HTML Shell, and Trusts Unvalidated Notification URLs
- **Location:** [`web/sw.js`](file:///Users/vattitude/Coding/Morning_Brief/web/sw.js#L27-L68) and [`web/sw.js`](file:///Users/vattitude/Coding/Morning_Brief/web/sw.js#L90-L98)
- **Root Cause:**
  1. In [`web/sw.js`](file:///Users/vattitude/Coding/Morning_Brief/web/sw.js#L27-L68), the `fetch` handler intercepts all same-origin `GET` requests except `/audio/` and `/briefings/`. It does **not** exclude `/api/*` (or `/s/*`). Consequently, `GET /api/geo` is cached inside `CACHE_NAME` by the Service Worker, and if a network error occurs, line 66 (`.catch(() => caches.match('/'))`) returns the HTML of `index.html` with HTTP 200 to `fetch('/api/geo')` callers!
  2. In [`web/sw.js`](file:///Users/vattitude/Coding/Morning_Brief/web/sw.js#L90-L98), `notificationclick` reads `const target = e.notification.data?.url || '/';` and passes it directly to `client.navigate(target)` or `self.clients.openWindow(target)` without validating that `target` is a relative path (`target.startsWith('/')`) or same-origin URL.
- **Remediation:**
  1. Add `if (url.pathname.startsWith('/api/')) return;` to the Service Worker `fetch` event listener, and only fall back to `caches.match('/')` when `e.request.mode === 'navigate'`.
  2. Restrict `notificationclick` navigation targets to same-origin paths (`new URL(target, self.location.origin).origin === self.location.origin`).

---

#### SEC-30 (Medium): Dead `api.uploadVoiceFile` Helper Uses Unsanitized `voiceId` Path
- **Location:** [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js#L643-L654)
- **Root Cause:**
  `uploadVoiceFile(voiceId, wavBlob)` builds `const path = "voices/" + voiceId + ".wav";` without validating `voiceId` against `/^[a-zA-Z0-9_-]+$/` and attempts to upload to the public `briefings` bucket. Because BYOK voice cloning was removed from the client app, this method is unused dead code.
- **Remediation:**
  Remove `uploadVoiceFile()` from [`web/js/api.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/api.js) (or enforce `/^[a-zA-Z0-9_-]{1,64}$/.test(voiceId)`).

---

#### SEC-31 (Low): Over-Privileged GitHub Actions `contents: write` Token, Unvalidated Tag Arithmetic, & Missing JS Security Tests in CI
- **Location:** [`.github/workflows/android.yml`](file:///Users/vattitude/Coding/Morning_Brief/.github/workflows/android.yml#L14-L55) and [`.github/workflows/tests.yml`](file:///Users/vattitude/Coding/Morning_Brief/.github/workflows/tests.yml#L1-L26)
- **Root Cause:**
  1. [`.github/workflows/android.yml`](file:///Users/vattitude/Coding/Morning_Brief/.github/workflows/android.yml#L14) grants `permissions: contents: write` at the job level even when triggered by `pull_request` or non-tag `push` to `main`.
  2. Lines 48–50 of `android.yml` parse `VERSION_NAME` and evaluate `$(( major * 10000 + minor * 100 + ${patch:-0} ))` in bash arithmetic without stripping pre-release suffixes (e.g., `1.0.22-rc1`) or validating digits (`^[0-9]+\.[0-9]+\.[0-9]+$`), and `$RUNNER_TEMP/release.jks` is not wiped in an `if: always()` cleanup step.
  3. [`.github/workflows/tests.yml`](file:///Users/vattitude/Coding/Morning_Brief/.github/workflows/tests.yml) lacks an explicit `permissions: contents: read` block and only runs `pytest`, completely skipping `npm test` (`node --test tests/js`), where all JavaScript security regression tests (`SEC-01`–`SEC-24`) reside.
- **Remediation:**
  1. Add `permissions: contents: read` to `tests.yml` and run `npm test` alongside `pytest`.
  2. Validate `VERSION_NAME` against `^[0-9]+\.[0-9]+\.[0-9]+$` in `android.yml` and delete `$RUNNER_TEMP/release.jks` in an `if: always()` step.

---

#### DATA-10 (Low): Hardcoded Admin Email Remaining in `web/js/pages/admin.js` & Unsanitized `last_run` in `public.app_status`
- **Location:** [`web/js/pages/admin.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/pages/admin.js#L216-L231) and [`app/worker.py`](file:///Users/vattitude/Coding/Morning_Brief/app/worker.py#L87-L91)
- **Root Cause:**
  1. While commit `b368cfb` removed `vatsakrish@gmail.com` from `web/js/api.js` and `supabase/schema.sql`, [`web/js/pages/admin.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/pages/admin.js#L216-L231) still hardcodes `vatsakrish@gmail.com` in `renderRestricted()` (shown directly to non-admin users who visit `/admin`) and `renderHeader()`.
  2. While `Worker.run_pack()` sanitized `last_pack` in `public.app_status`, `Worker.run_batch()` ([`app/worker.py`](file:///Users/vattitude/Coding/Morning_Brief/app/worker.py#L87-L91)) still writes `last_run=report.to_dict()` (including internal `failures` strings) to `public.app_status`, which is readable by all authenticated users.
- **Remediation:**
  Remove the hardcoded email from [`web/js/pages/admin.js`](file:///Users/vattitude/Coding/Morning_Brief/web/js/pages/admin.js#L216-L231) (use `profile?.email || 'Admin'` in `renderHeader()` and generic wording in `renderRestricted()`) and redact `failures` details from `last_run` in `public.app_status` (keeping full details in admin-only `public.run_log`).

