# Commit, push and version every change

After finishing any change to this repo:

1. Bump the version for what you touched:
   - Web (`web/`): increment `CACHE` in `web/sw.js` (`morning-brief-vN`).
   - Android (`android/`): bump `versionName`/`versionCode` as the release process requires.
   - Add an entry to `CHANGELOG.md`, numbered after the latest release (check `git tag` and the top entry).
2. Run the tests (`.venv/bin/python -m pytest -q`).
3. Commit with a clear message and `git push origin main`, without asking first.
4. State the new version in the reply.

Stage only the files you changed; leave unrelated working-tree changes alone.
