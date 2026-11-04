# Commit, branch, PR and version every change

After finishing any change to this repo:

1. Bump the version for what you touched:
   - Web (`web/`):
     - Update `export const APP_VERSION = 'vX.Y.Z';` in `web/config.js` (rendered in the hamburger menu drawer).
     - Update `<div class="clean-drawer-version" id="cleanDrawerVersion">Hark Daily vX.Y.Z</div>` in `web/index.html`.
     - Bump script cache query in `web/index.html` (e.g. `<script type="module" src="/js/app.js?v=N"></script>`).
     - Increment `CACHE` in `web/sw.js` (`hark-daily-vN`) so browsers and installed PWAs immediately activate the new shell.
     - Bump `"version"` in `package.json`.
   - Android (`android/`): bump `versionName`/`versionCode` in `android/app/build.gradle.kts`. Note: UI screens (e.g. `SettingsScreen.kt`) must always reference `BuildConfig.VERSION_NAME` dynamically—never hardcode version strings.
   - Add an entry to `CHANGELOG.md`, numbered after the latest release (check `git tag` and the top entry).
2. Run the tests (`.venv/bin/python -m pytest -q` and `node --test tests/js/*.test.mjs`).
3. **NO DIRECT PUSH TO MAIN**: Pushing directly to `main` is strictly prohibited.
   - Create and work on a feature/fix branch (e.g. `feat/...` or `fix/...`).
   - Push to that branch (`git push -u origin <branch-name>`).
   - Open or request a Pull Request (PR) for review and merging into `main`.
4. State the new version and branch/PR in the reply.
5. Always print the version at the end of every response so the user can confirm with the app after reload (e.g. `**App Version**: Hark Daily vX.Y.Z (SW: hark-daily-vN, Script: ?v=N)`).

Stage only the files you changed; leave unrelated working-tree changes alone.
