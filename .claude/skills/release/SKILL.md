---
name: release
description: >
  Full release of eos-fight-mon in one go: unit tests, VERSION in update.py,
  release commit "vX.Y.Z: ...", tag, push, Windows exe (PyInstaller) and
  Linux binary (WSL), SHA256SUMS.txt and release notes, gh release create,
  re-download and compare checksums, clean up dist, then "Handover: vX.Y.Z released".
  Only on an explicit /release.
disable-model-invocation: true
---

# Release eos-fight-mon

From working tree to a published GitHub release the self-updater can take.
Talk to the user in German; commits, tag, notes and files stay English.
Read `HANDOVER.md` first - its "Build and release" and "Gotchas" sections
are the reference; if they changed, they win over this file.

`gh` is logged in as `fthomas-de`; if it is not on `PATH`, call
`"C:\Program Files\GitHub CLI\gh.exe"`. Repo: `fthomas-de/eos-fight-mon`.

**The user may be playing.** Never open a window of the tool, never start,
kill or overwrite a running `dist\eos-fight-mon.exe`.

## 0 · Check the starting point

- `git fetch`; `git rev-list --count HEAD..@{u}` must be 0, else stop and
  show it (no rebase, no merge).
- `git status -s`: the changed files are this release. Untracked files you
  do not know: name them and ask, never take them along unasked.
- Version: `VERSION` in `update.py`. If the user names one, set exactly that.
  If it is not above the last tag (`git tag --sort=-v:refname | head -1`),
  bump patch +1. The tag must be free (`git tag -l`, `gh release view`);
  never move a tag or overwrite a release.
- What is in it: `git diff` / `git log <last tag>..HEAD`, plus what
  `HANDOVER.md` lists for this version.

## 1 · Tests

```bash
python -m unittest discover -s tests
```

Read the last lines. On failure: stop, show it, do not weaken tests.

## 2 · Build

1. `python tools/build_icons.py --check` compares the SDE build of `ship_icons.json` / `drones.py`
   with CCP's latest. Exit 1 (outdated): run `python tools/build_icons.py` (~100 MB download) and
   commit both files with the release.
2. Windows: if `dist\eos-fight-mon.exe` exists, **rename** it to
   `dist\eos-fight-mon-<its version>-prev.exe` (it may be running; renaming
   works, deleting does not; if that name is taken, add `-2`, `-3`, … -
   step 8 removes them again), then
   ```bash
   python -m PyInstaller --onefile --windowed --name eos-fight-mon --icon icon.ico --add-data "ship_icons.json;." main.py
   ```
   Do not start the exe (it opens windows).
3. Linux, with smoke test (headless server, one event, `--reset` must store
   the fight):
   ```bash
   wsl.exe -d Ubuntu -- bash /mnt/c/Users/floth/Documents/eos-fight-mon/tools/build_linux.sh
   ```
   The output must show the tick line and a file in `history`. Otherwise
   stop.

## 3 · Release folder

New folder `dist\release-<version>\` with

- `eos-fight-mon-v<version>-windows-x64.exe` (copy of `dist\eos-fight-mon.exe`)
- `eos-fight-mon-v<version>-linux-x86_64` (copy of `dist\eos-fight-mon-linux`)
- `SHA256SUMS.txt`: `sha256sum -b` of both, format `<hash> *<name>`

**Keep these names exactly** - the updater finds the asset by its suffix
`-windows-x64.exe` / `-linux-x86_64` and refuses without `SHA256SUMS.txt`.

- `RELEASE_NOTES.md` in the style of the previous release
  (`gh release view <last tag> --repo fthomas-de/eos-fight-mon`):
  one or two sentences, `## Downloads` table (file → for whom, with the
  version in the file names), the update note (from v0.5.0 the tool offers
  the update itself; v0.4.0 and older replace the exe by hand, keep
  `config.ini` and `history/`), `## New in v<version>` with bold lead-ins
  written for players, not file names.

## 4 · Ask or go

Go on without asking when the starting point was clean (no unknown files,
remote not ahead, tag free), tests and smoke test passed and nothing else
surprised. Otherwise ask once now - nothing has left the machine yet:

> Release v<version>: <keywords>. Stood out: <what>. Go ahead?

## 5 · Commit, tag, push

1. Stage by path (`git add <paths>`), never `git add -A`.
2. Message with the **Write tool** to `.git/CLAUDE_COMMIT_MSG` (no
   heredoc). Subject `v<version>: <what changed, short, comma-separated>`
   as in `git log --format=%s -8`; end with the attribution line from the
   session's system context. The file is left over from the last release,
   so **Read it first** (the Write tool refuses an existing file not read
   in this session). **Never put the Write and the commit in the same
   batch of parallel tool calls**: if the Write fails, the commit still
   runs and takes the old message. v0.6.3 went out as "Handover: v0.6.2
   released" that way, and a pushed message cannot be fixed without a
   force push.
3. Only after the Write succeeded, commit in a separate call, guarded by
   the subject:
   ```bash
   head -1 .git/CLAUDE_COMMIT_MSG | grep -qx "v<version>: .*" && git commit -F .git/CLAUDE_COMMIT_MSG
   ```
   Then `git log -1 --format=%s` must show that subject **before** anything
   is tagged or pushed - so no commit, tag and push in one command. Wrong
   subject: fix the file and `git commit --amend -F .git/CLAUDE_COMMIT_MSG`;
   nothing has left the machine yet.
4. `git tag v<version>`, then `git push origin main` and
   `git push origin v<version>`. Never `--force`. A refused push: stop, show.

## 6 · GitHub release

```bash
gh release create v<version> --repo fthomas-de/eos-fight-mon --verify-tag --title "v<version>" --notes-file dist/release-<version>/RELEASE_NOTES.md dist/release-<version>/eos-fight-mon-v<version>-windows-x64.exe dist/release-<version>/eos-fight-mon-v<version>-linux-x86_64 dist/release-<version>/SHA256SUMS.txt
```

## 7 · Check

Download into a new empty folder in the scratchpad and run
`sha256sum -c SHA256SUMS.txt` there. Windows downloads here sometimes get
reset (WinError 10054, also `gh release download`); then use WSL
`curl -L` on the asset URLs. A mismatch: show it, never delete the release
on your own. Problems after the push are fixed with a new patch version.

## 8 · Clean up dist

Only after step 7 passed (the assets are safe on GitHub then).

Keep: `eos-fight-mon.exe`, `eos-fight-mon-linux`, `release-<version>\`
of this release, and **never touch `config.ini` and `history\`** - that is
the user's own setup and fights.

Remove, each by name (no wildcard `rm -rf dist`):

- `eos-fight-mon-*-prev*.exe` (renamed in step 2) and test builds
  `eos-fight-mon-*-test*.exe`
- `eos-fight-mon.exe.*.old` left by the self-updater
- `release-<older version>\` folders
- `build\` and `eos-fight-mon.spec` in the repo root, if still there

A file that cannot be deleted is probably still running (the user may
have started an old build): skip it, never kill it, name it in the
summary. List `dist\` afterwards.

## 9 · Handover

Update `HANDOVER.md` ("Where things stand": latest release with URL and
date, what is not committed any more, what is open; move anything now
released out of the "done but not committed" part). Rewrite, do not
append. Commit `Handover: v<version> released` the same way as in step 5
(Read, Write, then in a separate call the guarded commit with
`grep -qx "Handover: v<version> released"`), check `git log -1`, push.

Also update the `eos-fight-mon-project` memory line "Released up to ...".

## 10 · Summary (German, ~6 lines)

- version old → new, commit, tag, release URL
- tests and Linux smoke test: result
- assets with sizes, checksums verified yes/no
- what the notes list (keywords)
- dist cleaned up: what was removed, what was skipped
- released without asking, or what stood out
