# Cindy CLI

## Scope And Status

`ai-assistant cindy` preserves the existing `cshare-to-markdown` API and adds
cold profile snapshots, integrity verification, transactional replacement,
retention, artifact resolution and verified downloads. Custom help is Chinese;
each enumerated option explicitly lists its values and meanings in `--help`.

This implementation deliberately distinguishes implemented machinery from
platform acceptance:

| Surface | Status |
|---|---|
| Existing cshare conversion | Preserved; help translated |
| POSIX backup / verify / restore / reset / recover | Implemented and tested with synthetic temporary profiles |
| TUI, plain fallback, prune, clear | Implemented; real POSIX PTY tests |
| Regional release resolution and download-only on POSIX | Implemented; real loopback HTTP tests |
| macOS DMG install / replace / uninstall | Implemented; requires official signature and identity checks, never launches Cindy |
| Windows storage mutations and native installation | Disabled until DACL, locking, junction and installer VM acceptance |
| Linux native user-install and desktop integration | Disabled until official script and protocol rollback acceptance |

No environment switch bypasses these gates. On Windows, local help and read-only
installation queries remain available; downloading on a POSIX host can target
Windows or Linux. Linux POSIX data operations do not execute installer scripts.
Do not interpret a successful loopback download as validation of an executable.

## Usage

```bash
ai-assistant cindy --help
ai-assistant cindy data backup --help
ai-assistant cindy install --help

# All Cindy instances must remain fully stopped for profile changes.
ai-assistant cindy data backup --region cn --label before-test
ai-assistant cindy data reset --region cn
ai-assistant cindy data restore --region cn
ai-assistant cindy recover

# Cross-platform download only; never executes the downloaded installer.
ai-assistant cindy install --region global --channel beta --platform win32 --arch x64 --mode installer --download-only

# Separate macOS program directories; not a userData override.
ai-assistant cindy install --region cn --dest "$HOME/Applications/Cindy-CN/Cindy.app"
ai-assistant cindy install --region global --dest "$HOME/Applications/Cindy-Global/Cindy.app"
ai-assistant cindy installs --json
```

`reset` already creates and verifies a `pre-reset` backup by default; a separate
manual backup is optional. `--no-backup` and `--no-pre-backup` skip only the
automatic backup, never integrity, confirmation or transactional checks.

`--backup-dir` selects a backup search directory. `--target` changes a restore
target and requires `--allow-relocate`. There is no ambiguous `--dir` option.
Explicit versions cannot be combined with `--channel`; channels select `latest`.

## Regional Coexistence

CN and Global use different CDN origins, macOS TeamIDs/bundle IDs, state records,
artifact cache directories and default installation IDs. Main userData remains
`Cindy` for CN and `CindyGlobal` for Global. Installing at a different program
path does not move either profile.

Distinct directories prevent this CLI from overwriting the other region's
program files. They do **not** make the official clients fully independent:

- Both clients use the visible name Cindy and the `cindy` / `xdt-maker` schemes.
- Clients can register protocol handlers themselves when starting; portable does
  not imply registry-free runtime behavior.
- Windows official installers can touch same-named shortcuts, context menus,
  startup entries and processes. Their appIds alone do not isolate these effects.
- Profiles share `appData/Cindy/shared-*` and can share OS keychain identities.
- Automatic updates remain enabled. Separate directories do not guarantee that
  every historical updater avoids cross-region interference.

Do not rename signed executables, modify ASAR or block updates to mask these
limitations. Dual-region launch/login/update/uninstall acceptance is still an
external platform gate, especially for Windows installer mode.

## Profile And Path Boundaries

Region is explicit for installation and main-profile selection. `--path` can
infer only exact Cindy/CindyGlobal/CindyDev and their `-dev2[-name]` forms.
Unknown custom names require `--region`. A developer-isolated profile is not
necessarily the `dev` region.

The profile record includes region, kind (main/isolated/custom), name, original
path, appData, platform, native architecture and non-secret `keychain-identity`.
Only complete `Cindy\n` / `CindyDev\n` marker contents are recognized. OS keys
are never read, exported or decrypted. Restores require the same platform and
native architecture; same schema number is only a compatibility screening.

Restoring an isolated profile does not target the main profile. Relocation
cannot cross kinds or regions, overwrite unknown nonempty custom data, or
rewrite absolute links/database paths. Unlocatable original paths require an
explicit destination. Changed keychain identities fail closed.

Roots cannot be links, junctions, filesystem roots, mount roots, HOME, appData or
Applications containers. Network filesystems are rejected. Sources, state,
backups and installs must not overlap, except for the managed backups/downloads
inside the state root. Sensitive storage is forbidden inside Git worktrees,
even ignored paths. Label text never becomes an unchecked path.

## Private State

`AI_ASSISTANT_CINDY_HOME` overrides the absolute state root; otherwise use
`${XDG_STATE_HOME:-~/.local/state}/ai-assistant/cindy`. `CINDY_HOME` is not an
additional environment variable.

```text
backups/       archives, partial ownership records and rebuildable index.json
downloads/     region / platform-arch / artifact-kind / digest / package
profiles.json explicitly selected profiles
installs.json installation provenance and directory identities
undo.json      last pre-operation backup per profile
journal/       in-progress transaction records
cache/         bounded GitHub metadata, fresh for ten minutes
```

POSIX private directories start at 0700 and state/archives at 0600. A per-user
runtime lock lives outside the configurable state root so two different state
roots cannot operate concurrently. Active transaction locators in that same
runtime directory prevent changing state roots to bypass interrupted work.
OS-released `flock` locks are never replaced by PID-file guesses.

The CLI lock cannot prevent Cindy itself from starting. Process evidence has
stopped/busy/unknown states; unknown does not mean stopped. All Cindy regions
must stay stopped while copying, activating or cleaning a profile or replacing
an installation. Processes are never killed. Tests inject fixture executable
names only through library APIs, not a production CLI bypass.

## Archive Version 1

PAX tar with optional zstd/gzip contains:

1. `cindy-backup.json`: bounded format/identity/count/exclusion/provenance header.
2. `data/` members: directories, regular files and links; no traversal.
3. `cindy-files.jsonl`: header digest and an exact ordered record of each member,
   including SHA-256 for every regular file and the target of every link.

An entire-archive SHA-256 is also stored in the index. A copied archive still
verifies without its original index; counts and tar header checksums alone never
constitute content integrity. Embedded hashes detect damage, not malicious
replacement by an untrusted author. Only restore trusted backups.

Default bounds are 100 GiB / 200,000 members, explicitly adjustable with
`--max-bytes` and `--max-entries`. Additional fixed bounds cover metadata, paths
and decoder windows. PAX extension size is checked before parsing. Duplicate,
case/Unicode-colliding paths, sparse/hardlink entries, device files, FIFOs, ADS,
UNC, drive names, reserved names, and link ancestors are rejected. Links are
created last, so no extraction write follows an archived link.

Absolute, relative and dangling links are retained without following targets.
Source hardlinks become independent files. UID/GID, xattr, ACL, ADS and setid
bits are not preserved. Root access remains private; this is a content snapshot,
not a disk image. Windows junction restoration remains gated.

Runtime Singleton entries and update-cache contents are excluded by default.
`--exclude-caches` affects the named top-level browser caches only. Persistent
application data, DB/WAL/SHM and migration/keychain identity sidecars remain.
DB schema screening reads disposable copies, never checkpoints a live DB.

A backup writes a unique `.partial`, records its ownership, closes and syncs the
compressor, verifies all content, rechecks the source and processes, then
publishes and indexes. Failed partials remain identifiable for interactive clear.
Unknown partials are not deleted automatically. Index publication failure reports
the successful archive path and a non-success status instead of hiding it.

## Replacement Transaction

A private same-volume wrapper holds `new` and `old`. The journal is persisted
before any original data is moved. CN main restores copy current `shared-*` into
staging by default, checking the copy; nothing is moved out of the current tree.
`--include-shared` is valid only for CN main -> CN main and explicitly rolls back
shared state used by other regions. Reset creates an empty or shared-only root.

```text
preparing -> prepared -> moving-old -> old-moved -> activating
          -> activated -> cleanup-pending -> done
```

Each rename is no-replace (Linux renameat2 / macOS renamex_np). Two renames do
not form a single atomic operation. Recovery compares parent/wrapper/old/new
filesystem identities and infers activation even if its following journal write
never occurred. Before activation it rolls back; after activation it only
finishes state publication and cleanup. Partially deleting old cannot invalidate
new or trigger rollback to a partial old tree.

A foreign/recreated target, damaged journal or missing ownership evidence stops
recovery and preserves all data. Repeated recovery is idempotent. Mac install
replacement moves old to the OS trash after commit; failure retains old for
recovery. Directory uninstall has its own activation semantics and never deletes
profile data. Power-loss durability remains filesystem-dependent.

## Retention And Interaction

Candidates read bounded headers only and remain marked unverified until a full
read. Plain terminal selection is available without questionary, or with
`AI_ASSISTANT_CINDY_TUI=plain`; it never bypasses TTY requirements.

`prune` groups by profile identity, retains latest N (N >= 1) plus the latest
undo backup, and verifies retained archives before deleting any older ones.
`clear` requires a real TTY and exact `delete N`, lists the scope, warns about
last backups/undo points, and never accepts `--yes`. Only first-level regular
files with validated identity/ownership can be removed. Active transactions
block cleaning. Individual deletion failures are reported with partial results.
Cancellation before writes is success with no changes; interruption after writes
reports interruption/recovery, not a false no-op claim.

## Artifact Trust

The resolver binds region, platform, architecture, version, mode, artifact kind,
URL, size and expected digest. ZIP and Setup.exe are different artifacts.
Historical portable ZIPs without a trustworthy ZIP digest are rejected; a
GitHub EXE digest can never authenticate one. GitHub source needs the exact
matching asset and never silently changes mode.

All downloads require a trusted SHA-256 except explicit local macOS
`--allow-signature-only`. That exception still requires the official app TeamID,
bundle ID, exact version, architecture, codesign and Gatekeeper verification;
it never permits a digest mismatch. Download-only always requires SHA-256 and
does not claim native signature verification.

HTTP uses TLS, bounded retries and allowed-origin redirects. GitHub tokens are
optional and only reach the official API origin, never CDN/assets/overrides or
logs. Strong ETag / Range / If-Range bind resumable data to the exact artifact.
200 restarts, 206 verifies the byte interval, and 416 only publishes an already
complete file after digest verification. Cached bytes are rehashed before reuse.
The file limit is 2 GiB. Loopback-only HTTP overrides support deterministic local
tests without disabling TLS for real services.

## Validation And Remaining Gates

Focused tests use real temporary files, SQLite, child process death, OS locks,
PTYs, and loopback HTTP servers. They never launch Cindy, execute a downloaded
installer, touch a real user profile, alter protocol handlers, uninstall an app,
or access a keychain. Cross-platform CI runs focused tests and a no-extra check.
Windows mutation tests explicitly skip while that platform gate is closed.

Run:

```bash
uv run pytest -q tests/cindy_test.py tests/cindy_*_test.py
uv run pytest -q
uv run tox
uv run pre-commit run --all-files
uv run typer --app cmd ai_assistant.commands.main utils docs --name ai-assistant --output docs/COMMANDS.md
uv build
```

Native signed DMG acceptance and Windows/Linux VM acceptance must be recorded
separately from these tests. Windows NSIS, Linux stable-prefix script recovery,
and desktop/protocol restoration are intentionally not exposed as working
adapters until their external side effects can be validated. Do not use an
unsafe fallback to complete a release checklist.

### Local Feasibility Evidence

The implementation was exercised on macOS with no real profile mutations:

- The original eight cshare tests pass unchanged.
- The final cross-version tox run passes on Python 3.10, 3.11, 3.12, 3.13 and
  3.14; the repository suite reports 561 passed / 22 skipped on each interpreter.
- Fresh isolated minimal environments on Python 3.10 and 3.14 explicitly assert
  that questionary and zstandard are absent, then pass 79 tests / 1 optional
  zstandard test skipped. Python 3.14's standard-library zstd path is exercised.
- Real PTY tests cover cancellation and exact deletion confirmation. Child
  processes are terminated at transaction boundaries and recovered repeatedly.
- A generated unsigned DMG is mounted read-only, rejected by the actual system
  signature checker, detached, and rolled back without an installation record.
- Read-only validation of an existing official CN 0.1.120 application passes
  codesign, Gatekeeper, TeamID and bundle ID checks. The application is not
  started or modified, and no profile or keychain is inspected.
- Native installation of an official DMG, replacement of a daily-use app, OS
  trash behavior and real uninstall have deliberately not been executed.
  Global signed-bundle acceptance and Windows/Linux VM gates remain outstanding.

These results establish local feasibility, not completion of every native
side-effect acceptance test. They do not authorize running real installers as
part of ordinary pytest or enabling a disabled adapter.
