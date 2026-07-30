# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`infinidat.infinibox` — an Ansible Collection of 21 modules (`plugins/modules/infini_*.py`) that manage Infinidat InfiniBox storage arrays via the `infinisdk` Python library. Modules are CRUD-style (`present`/`absent`) with idempotency, plus a `stat` state on most modules for read-only inspection. A few modules add extra states (`search`, `search_iboxes`, `login`, `rename`).

The collection is published to Ansible Galaxy as `infinidat.infinibox` and to Red Hat Automation Hub.

## Common commands

The `Makefile` is the source of truth — run `make help` to see all targets with descriptions. Highlights:

```bash
# Setup (venv required; setup target enforces this)
make setup                    # installs ansible, infinishell, project deps

# Sanity tests (the CI gate — required to pass before a release)
make test-sanity-locally      # builds collection, installs locally, runs ansible-test sanity

# Playbook-based integration tests — these need vault_password.txt + a real iBox
make test-create-resources    # primary smoke test; creates many resources, checks idempotency
make test-remove-resources    # tear-down counterpart; also checks idempotency on remove
# Other test-{create,remove}-{snapshots,volumes,metadata,map-cluster,...} pairs follow the same pattern

# Build & publish to Galaxy
make galaxy-collection-build  # produces infinidat-infinibox-X.Y.Z.tar.gz
make galaxy-collection-publish # needs GALAXY_API_KEY in ~/.ssh/ansible-galaxy.sh

# CI image (psusdev/gitlab-cicd:v0.16) — built from ci/Dockerfile
make ci-image-build
make ci-image-deploy-hints    # prints scp + load steps for the runner host

# Module hacking — debug a single module locally with a prepared JSON input
make dev-hack-module-present  # also: -stat, -absent, -search, -login, -rename, with -jq variants
```

To run a single playbook test other than the wrapper recipes, follow the `_test-playbook` pattern in `Makefile`: it cd's into `playbooks/`, installs the collection from `$PWD/..`, then `ansible-playbook --extra-vars @../$(_extra_vars) --vault-password-file ../vault_password.txt $$playbook_name`. `_extra_vars` defaults to `ibox_vars/iboxCICD.yaml`; override at the make invocation.

## Architecture

### Module pattern
Every `plugins/modules/infini_*.py` follows a tight idiom you should match when adding or editing modules:

1. **Argument spec → `state` is mandatory**, with values like `present`, `absent`, `stat`. Module-specific states are layered on top.
2. **All InfiniBox API calls are decorated with `@api_wrapper`** (defined in `plugins/module_utils/infinibox.py`). It catches `SystemNotFoundException`, `APICommandException`, and bare `Exception`, then funnels them into `module.fail_json(msg=...)`. Don't catch these manually — let the decorator do it.
3. **`infinisdk.InfiniBox`** is the connection object. It's typically built once via the `get_system()` helper in `module_utils/infinibox.py`, which honors the `stay_logged_in` option that pickles the session to `/tmp/infinibox_pickle_<IBOX>` for reuse across module invocations (see psdev-1330 in CHANGELOG).
4. **Idempotency is enforced in module code, not by the API.** A `present` call must check current state first and only act on diff; a `stat` call must never write. The integration playbooks (`test_create_*.yml`) re-run themselves to verify idempotency — breaking it will surface as a `changed: true` on the second run.
5. **`urllib3.disable_warnings(InsecureRequestWarning)`** — InfiniBoxes typically use self-signed certs; this is intentional in `module_utils/infinibox.py`.

### Tests are playbooks, not pytest
There is **no Python unit test suite**. "Tests" are pairs of Ansible playbooks in `playbooks/` (`test_create_X.yml` / `test_remove_X.yml`) that exercise modules end-to-end against a real InfiniBox. Each playbook runs its tasks twice in the same play to assert idempotency.

The `tests/` directory is for `ansible-test sanity` only (which checks docs, lint, FQCN, etc. against a synthetic collection install) and `tests/hacking/` JSON fixtures for `make dev-hack-module-*`.

`playbooks/ansible.cfg` is what makes in-tree development work — it points `library`, `module_utils`, etc. at the source tree so playbooks resolve modules from `plugins/` without a galaxy install. Keep that file in sync if you reorganize plugin layout.

### Module hacking workflow
For interactive debugging of a single module without a full playbook run:

1. Set `_module_under_test = infini_X` near the top of the `##@ Hacking` section of `Makefile`.
2. Have an Ansible source clone at `~/workspace/ansible` (path is hard-coded in `_ansible_clone`).
3. `make dev-hack-create-links` symlinks the plugin files into the Ansible clone's module path.
4. Drop a JSON fixture in `tests/hacking/<module>_<state>.json` matching the state you want to test.
5. `make dev-hack-module-{state}` runs the module with that JSON as stdin. Add `-jq` suffix to pretty-print result. `breakpoint()` works for pdb.

### CI topology (post-psdev-1437)
`.gitlab-ci.yml` runs against:
- **Runner host**: `psus-ansible-runner` (Ubuntu 22.04 / Jammy), gitlab-runner with `docker` executor talking to **rootless podman** via `unix:///run/user/<uid>/podman/podman.sock`. Runner tag is `jammy-podman`.
- **Image**: `psusdev/gitlab-cicd:v0.16` built from `ci/Dockerfile` (Ubuntu 24.04 base, Python 3.12; bumped in psdev-1438). The image is **not pushed to any registry** — it's built directly on the runner host as the `gitlab-runner` user. `pull_policy = "if-not-present"` in `/etc/gitlab-runner/config.toml` is what makes the runner use the local image instead of trying to pull. If you bump the image, build it on the runner before merging the `.gitlab-ci.yml` change.
- **Vault secret**: `VAULT_PASSWORD_FILE` is a CI variable of type "File" with the ansible-vault password for `ibox_vars/iboxCICD.yaml`.

### Versioning & releases
- **Single source of truth for version**: `galaxy.yml` (`version:` field, currently `1.8.0`). The Makefile reads it via `spruce json galaxy.yml | jq '.version'`.
- **`meta/runtime.yml` `requires_ansible`** must stay in lockstep with the ansible-core floor in `requirements-dev.txt` (both currently `2.18`). Bump them together.
- **`make releasable`** is the preflight gate — it requires:
  - No literal "TBD" in `CHANGELOG.rst`
  - Git working tree clean
  - HEAD pushed to origin
  - A tag `v$(version)` exists locally
  - That tag's commit matches HEAD
  - The tag is also on origin and matches the local tag commit
- Bumping the ansible-core floor → bump the minor version (1.X.0); confirmed pattern with v1.7.0 / psdev-1437 and again v1.8.0 / psdev-1438 (floor raised to ansible-core 2.18).

## Project conventions

- **Commit messages**: prefix with the Jira ticket — `psdev-NNNN:` or `psus-NNNN:`. CHANGELOG bullets carry the same prefix per line.
- **Branch**: `develop` is the integration branch. Tags (`vX.Y.Z`) are cut from develop.
- **Module copyright header** matches `Copyright: (c) <year>, Infinidat <info@infinidat.com>` + GPL-3.0+. New modules should follow.
- **Pylint disables**: modules and `module_utils` carry intentional pylint disables at the top — see existing files for the pattern, don't reinvent. Sanity tests will fail on undeclared deviations.
- **No co-author trailers** in commit messages (per project convention).

## Things that look weird but are intentional

- **`requirements.txt` vs `requirements-dev.txt` are split by purpose** (cleaned up in psdev-1438): `requirements.txt` is *runtime only* — `infinisdk>=225.1.1`, its transitive deps kept explicit for reproducibility, plus `setuptools<81`. The `setuptools<81` pin is load-bearing: infinisdk 289.x still imports `pkg_resources`, which setuptools 81+ removed, so without it modules fail at runtime with `ModuleNotFoundError: No module named 'pkg_resources'`. Dev tooling (`pylint`, `black`, `pytest`) and the ansible pins (`ansible-core>=2.18,<2.19`, `ansible>=11,<12`) live in `requirements-dev.txt`. Keep runtime and tooling on their respective sides.
- **`infinishell`** appears in many Makefile recipes — it's an Infinidat CLI separate from infiniSDK, installed via `apt` from `repo.infinidat.com`. Used for ad-hoc operations the modules don't yet cover (see `infinishell-network-space-iscsi-create` etc.).
- **`Makefile-vars`** is gitignored and `-include`d for ad-hoc local overrides. Don't add it to git.
- **`session_pickle` files at `/tmp/infinibox_pickle_<IBOX>`** — these are real session credentials in pickled form. Created when `stay_logged_in: true` is set on a module. Cleaned up only when the module sets state appropriately. If you see one in a debug session, that's why.
