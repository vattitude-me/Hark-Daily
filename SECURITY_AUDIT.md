# Hark Daily (`Morning_Brief`) — Full Repository Security & Data Risk Audit

**Last Updated:** November 11, 2026 (Post-Commit `5b03088` & `524e0c4` Verification + Phase 2 Deep Audit)  
**Scope:** Full repository (`web/`, `web/api/`, `app/`, `voice_service/`, `android/`, `ios/`, `scripts/`, `supabase/`, `.github/workflows/`, and Git history)

---

## 1. Phase 1 Remediation Review (Verification of Commit `5b03088`)

We reviewed commit `5b03088` (`fix(security): resolve all critical, high, and medium audit findings (SEC-01 - SEC-14)`) line-by-line. While 11 of the 14 original items were cleanly resolved, **3 fixes contain subtle logic flaws or incomplete patches** that still leave attack vectors open:

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
