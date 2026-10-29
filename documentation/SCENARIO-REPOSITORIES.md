# Plugin repositories and plugin release packages

`sas-validation` installs scenario **plugins** from **plugin repositories** (GitHub or GitLab
projects that publish Releases). This document covers:

1. [Adding a public or private repository](#part-1---adding-a-repository) to `scenario-repositories.yaml`.
2. [The specification for a plugin release package](#part-2---release-package-specification): what the
   archive must contain, how it must be packaged, and how to publish it.

For day-to-day command usage see [CLI-CHEATSHEET.md](../CLI-CHEATSHEET.md).

---

## Part 1 - Adding a repository

### How it works

A repository alias in `scenario-repositories.yaml` points the CLI at a GitHub or GitLab project
that publishes **Releases**. The CLI calls the provider's HTTPS Releases API, finds the release
whose tag matches `--version`, downloads its `.tar.gz` asset, and extracts it into the installed
plugins directory, under a folder named after the repository alias.

The CLI reads `./scenario-repositories.yaml` by default. Use the global option
`--repositories <path>` to point at another file.

```yaml
# Used by `plugins install` and `plugins uninstall` when --repo is omitted.
default-repository: platform-scenarios

scenario-repositories:
  platform-scenarios:
    provider: github-release
    repository: owner/project
    visibility: public
```

| Field                | Required | Description |
|----------------------|----------|-------------|
| `provider`           | yes      | `github-release` or `gitlab-release`. |
| `repository`         | yes      | Project path: `owner/project` on GitHub, `group[/subgroup]/project` on GitLab. |
| `visibility`         | no       | `public` (default), `internal`, or `private`. Documentation only; access is decided by the token. |
| `base-url`           | no       | GitHub: API URL for GitHub Enterprise (default `https://api.github.com`). GitLab: instance URL (default `https://gitlab.com`). |
| `default-repository` | no       | Top-level key. Must name an alias in the file. Lets you omit `--repo` on `plugins install` and `plugins uninstall`. |

Alias names are what you pass to `--repo`. They also name the folder plugins from that repository
install into, so use only letters, digits, `.`, `_`, and `-`. Run `sas-validation plugins list-repos`
to see the configured aliases.

`default-repository` belongs at the top level of the file, next to `scenario-repositories:`.
Setting it inside an alias has no effect; the CLI ignores unknown keys there.

### Adding a public repository (GitHub)

No token is needed.

```yaml
scenario-repositories:
  platform-scenarios:
    provider: github-release
    repository: my-org/my-scenarios-project
    visibility: public
```

Unauthenticated GitHub API requests are rate limited. If you hit the limit, set
`SAS_VALIDATION_RELEASE_TOKEN` to a GitHub token; the CLI sends it as a bearer token.

### Adding a private repository (GitLab)

```yaml
scenario-repositories:
  private-scenarios:
    provider: gitlab-release
    repository: my-group/my-scenarios-project
    visibility: private
    base-url: https://gitlab.example.com
```

**Do not use the SSH clone URL as the repository.** The CLI does not run `git clone`; it uses the
HTTPS Releases API. Convert a clone URL like this:

| Clone command                                                  | Becomes                                              |
|----------------------------------------------------------------|------------------------------------------------------|
| `git clone git@gitlab-mygroup:my-group/my-scenarios-project`        | `repository: my-group/my-scenarios-project`          |
| `Host gitlab-mygroup` / `HostName gitlab.example.com` in `~/.ssh/config` | `base-url: https://gitlab.example.com`           |

The part after the `:` is the `repository` value. The real host name comes from the `HostName`
line of the SSH alias in `~/.ssh/config`.

#### Authentication

For `gitlab-release` repositories the CLI looks for a token in this order and uses the first one
it finds:

1. The `SAS_VALIDATION_RELEASE_TOKEN` environment variable.
2. Your GitLab CLI login (`glab auth login --hostname <host>`).
3. The git credential helper for the repository host (for example a cached HTTPS clone login).

Tokens are looked up per GitLab host, so one token serves every alias on that host. They are
never written to `scenario-repositories.yaml`.

The simplest setup is a one-time login with the [GitLab CLI](https://gitlab.com/gitlab-org/cli):

```bash
glab auth login --hostname gitlab.example.com
sas-validation auth status --repo private-scenarios   # names the source; never prints the token
```

Alternatively, create a token in GitLab under **Preferences > Access Tokens** and export it in
the shell where you run the CLI:

```bash
export SAS_VALIDATION_RELEASE_TOKEN='glpat-...'
```

Either way, the token needs the **`read_api`** scope, and the user must be able to see the
project's releases.

### Verify the repository

```bash
sas-validation plugins list-repo-plugins --repo private-scenarios
sas-validation plugins install --repo private-scenarios --version 2026.09
sas-validation plugins list
sas-validation plugins validate
```

- `--version` is the plugin version, for example `2026.09`. Release tags are published as
  `v` + the version (`v2026.09`); the leading `v` is optional everywhere on the CLI
  (`plugins install`, `plugins uninstall`, `--plugin-version`). `plugins install` looks the
  release up by the tag exactly as typed first, then with the `v` added or removed.
- Plugins install into `sas-validation.installed-plugins.destination` from `sas-validation.yaml`
  (or `--destination`). The older `installed-packages` key is still accepted. With no setting,
  they install into the user cache directory, under `sas-validation/packages`.
- Each install creates `<destination>/<repository-alias>/<archive top-level directory>/`, plus a
  `.sas-validation-plugin.yaml` install record naming the repository alias, tag, and asset. The
  record is how `plugins list-repo-plugins` and `plugins uninstall` know which repository a
  plugin came from, even when two repositories publish the same cadence. Plugins installed
  directly under the destination by older CLI versions are still found; they are matched to a
  repository by the `repository` field of their `release-manifest.yaml`.
- Remove a plugin with `sas-validation plugins uninstall --repo <alias> --version <version>`.
- Release archives are not cached. `plugins install` always downloads the archive into a temporary
  directory, extracts it into the destination, and deletes the download.

### Troubleshooting

| Message or symptom | Cause and fix |
|--------------------|---------------|
| `No access token found for GitLab repository ...` | No token source has a token. Run `glab auth login --hostname <host>` or set `SAS_VALIDATION_RELEASE_TOKEN`. |
| `HTTP Error 401` / `403` | Token expired, revoked, or missing `read_api`. The message names where the token came from. Renew it with `glab auth login`, or fix or unset a stale `SAS_VALIDATION_RELEASE_TOKEN`, which takes precedence over `glab`. |
| `HTTP Error 404` on `plugins list-repo-plugins` | Wrong `repository` path or `base-url`, or the token's user cannot see the project (GitLab returns 404 for projects you cannot access). |
| `HTTP Error 404` on `plugins install` | The project has no release for that tag. Run `plugins list-repo-plugins --repo <alias>` to see valid versions. |
| `Release '<tag>' contains no .tar.gz asset` | The release has no asset whose name ends in `.tar.gz`. On GitLab the file must be attached as a release asset **link**. See Part 2. |
| `Release '<tag>' has multiple .tar.gz assets` | Publish exactly one `.tar.gz` per release. |
| `... is already installed at ...` / `Installation target already exists` | That plugin version is already installed from this repository. Remove it first with `plugins uninstall`. |
| `must contain exactly one top-level directory holding release-manifest.yaml` | The archive is flat or has several top-level directories. Repackage it as described in Part 2; nothing is left installed. |
| `Repository alias '<x>' is not configured` | The alias is not in the `scenario-repositories.yaml` being read. Check the file and `--repositories`. |
| `default repository alias '<x>' is not configured` | `default-repository` names an alias that does not exist. |
| TLS or certificate error | Python does not trust your internal CA. Set `SSL_CERT_FILE` to a bundle that includes it. |
| `'scenario-repositories' must be a mapping` | The YAML is malformed. Compare it with `scenario-repositories.yaml.template`. |

---

## Part 2 - Release package specification

A **release package** is a gzip-compressed tar archive of one directory that holds a
`release-manifest.yaml`, the scenarios it lists, their workload definitions, and their resources.
One release in the hosting repository carries one package.

### Release requirements

| Item | Requirement |
|------|-------------|
| Tag | One release per tag. Convention: `v` + the package version, for example `v2026.09`, so the tag does not clash with a branch named `2026.09`. Users pass the version with or without the `v`; `plugins list-repo-plugins` shows it without the `v` (JSON output has both `version` and `tag`). |
| Version scheme | `YYYY.MM[.PATCH]`. `YYYY.MM` is the SAS Viya cadence the package targets. The first release of a cadence has no patch (`2026.09`); fixes add one starting at 1 (`2026.09.1`). `2026.09.0` is not valid. |
| Archive asset | **Exactly one** asset whose name ends in `.tar.gz`. |
| Other assets | Allowed and ignored by the installer, for example `<archive>.tar.gz.sha256`. |
| Asset name | Free-form, but the convention is `<name>-<version>.tar.gz`. |

Hosting specifics:

- **GitHub:** upload the archive as a release asset. The CLI uses its `browser_download_url`.
- **GitLab:** the archive must appear under the release's **assets links** (`assets.links` in
  the API), either as an uploaded generic-package link or an external URL. The automatic
  "Source code" archives that GitLab adds to every release are **not** used.

### Archive format

The archive is read by `tarfile` with automatic compression detection, but publish plain `.tar.gz`.

Rules enforced by the installer. A violation aborts the install and nothing is written:

| Rule | Detail |
|------|--------|
| No links | Symbolic links and hard links are rejected. |
| Regular files and directories only | Devices, FIFOs, and other member types are rejected. |
| No path escapes | Absolute paths and `..` entries that would extract outside the destination are rejected. |
| No overwrite | If a top-level entry already exists in the destination, the install fails with `Installation target already exists`. |

**Use exactly one top-level directory, named `<name>-<version>`, that holds `release-manifest.yaml`.**
`plugins install` rejects any other layout (for example a flat archive whose files sit at the
archive root) and removes whatever it extracted, because the CLI discovers a plugin only as a
directory that directly contains `release-manifest.yaml`.

Do not include macOS metadata (`._*` files, `.DS_Store`), `.git`, virtual environments, caches
(`__pycache__`), generated output, or secrets such as `sas-validation.yaml` or user files.

### Required layout

```text
sas-validation-scenarios-platform-2026.09/        <- single top-level directory
├── release-manifest.yaml                         <- required, at the package root
├── README.md                                     <- recommended
├── CHANGELOG.md                                  <- recommended
├── scenarios/                                    <- one directory per scenario
│   ├── common/                                   <- optional plugin-wide libraries (plugin-common)
│   │   └── plugin_helpers.py
│   ├── helloviya-simple/
│   │   ├── scenario-config.yaml                  <- scenario metadata (or scenario-manifest.yaml)
│   │   └── tests/
│   │       ├── logonoff.py                       <- entrypoints
│   │       └── createcompute.py
│   └── application-scenarios/
│       └── sas-studio/ ...                       <- scenarios may be nested at any depth
├── workload-definitions/                         <- *-wrkld-def.yaml files
│   └── helloviya-simple-wrkld-def.yaml
└── resources/                                    <- data, programs, and other shared inputs
```

`release-manifest.yaml` must be at the package root. `workload-definitions/` and `resources/` are
fixed names the loader uses, so keep them. Scenario directories can live anywhere, because
`release-manifest.yaml` gives each scenario's path; `scenarios/` is the convention.

### `release-manifest.yaml`

```yaml
schema-version: "1"
name: platform-scenarios
version: "2026.09"
viya-cadence: "2026.09"
repository: my-group/my-scenarios-project

scenarios:
  - id: helloviya-simple
    path: scenarios/helloviya-simple
  - id: sas-studio
    path: scenarios/application-scenarios/sas-studio
```

| Field | Required | Rules |
|-------|----------|-------|
| `schema-version` | no | Defaults to `"1"`. Any other value is rejected. |
| `name` | yes | Non-empty string. Together with `version`, identifies the plugin in `plugins list`. |
| `version` | yes | Non-empty **quoted** string. Used by `--plugin-version`. Keep it equal to the release tag without the `v`. |
| `viya-cadence` | yes | Non-empty **quoted** string, for example `"2026.09"`. |
| `repository` | yes | Non-empty string; the source project path. |
| `scenarios` | yes | Non-empty list. Each entry needs `id` and `path`. |
| `scenarios[].id` | yes | Unique within the manifest. Must match the `id` inside the scenario's own config file. |
| `scenarios[].path` | yes | Directory of the scenario, relative to the package root. No absolute paths and no `..`. |

### Scenario metadata

Each scenario directory holds `scenario-config.yaml`. The loader also accepts
`scenario-manifest.yaml` and checks it first if both exist, but `scenario-config.yaml` is
preferred: it also carries the `dependencies` list the workload generator reads, which
`scenario-manifest.yaml` does not.

The values may be at the top level or nested under a `scenario-config:` key.

```yaml
scenario-config:
  id: helloviya-simple                  # must equal the id in release-manifest.yaml
  display-name: Hello Viya Simple
  runtime: locust
  entrypoints:                          # or a single `entrypoint: tests/logonoff.py`
    - tests/logonoff.py                 # relative to this scenario directory
    - tests/createcompute.py
  workload-definitions:                 # relative to the PACKAGE root
    - workload-definitions/helloviya-simple-wrkld-def.yaml
  required-resources: []                # relative to the PACKAGE root; files or directories

  # Read by the workload generator
  name: hello-viya-simple
  description: Simple logon and logoff test using saslogon
  dependencies:
    - type: common
      path: framework/execution/common
      file: events.py
    - type: plugin-common                # library shipped in this plugin
      path: scenarios/common             # relative to the PACKAGE root
      file: plugin_helpers.py
```

| Field | Required | Rules |
|-------|----------|-------|
| `id` | yes | Must equal the manifest `id`. |
| `display-name` | yes | Non-empty string. |
| `runtime` | yes | Non-empty string, for example `locust`. |
| `entrypoint` / `entrypoints` | yes | String or non-empty list of strings. Each file must exist under the scenario directory. |
| `workload-definitions` | no | List of paths relative to the package root. Each file must exist. |
| `required-resources` | no | List of paths (or `{path: ...}` mappings) relative to the package root. Each file or directory must exist. |
| `dependencies` | no | Files added to the workload's config map. Types: `common`, `plugin-common`, `resource`, `cli-profile`, `trusted-certs`. See [Dependency types](#dependency-types). |

All paths must be safe relative paths: no leading `/`, no `..`.

#### Dependency types

Each entry has `type`, `path`, and `file`. The file is found at `<base>/<path>/<file>`:

| Type | Base for `path` | Use |
|------|-----------------|-----|
| `common` | The CLI `framework/` directory (a leading `framework/` is stripped). | Shared libraries shipped with the CLI, for example `framework/execution/common/auth.py`. |
| `plugin-common` | The **package root** (the directory holding `release-manifest.yaml`). | Shared libraries shipped with the plugin and reused by several of its scenarios, for example `scenarios/common/plugin_helpers.py`. |
| `resource` | The scenario directory. | Scenario-specific files. |
| `cli-profile` | The CLI `framework/` directory. | A sas-viya-cli profile template filled with the hostname. |
| `trusted-certs` | Not used; the file comes from the `trusted-certs` execution setting. | Adds the trusted certificates file to the config map. |

A scenario can list both `common` and `plugin-common` entries. All config map files are mounted
in one flat directory (`/lotest/src`), so tests import them by module name
(`from plugin_helpers import *`) and file names must be unique: workload generation fails if a
`plugin-common` file has the same file name as another file in the config map, for example a
plugin `studio_actions.py` next to the CLI's `studio_actions.py`. Rename the plugin file instead.

`plugin-common` paths must be safe relative paths, and `plugins validate` checks that each file
exists in the package.

> **Quote version numbers.** YAML reads an unquoted `version: 2026.09` as the number 2026.09
> (and `2026.10` as `2026.1`), and the CLI rejects it with `'version' must be a non-empty string`.

### Workload definitions

Files in `workload-definitions/` ending in `.yaml` or `.yml` are listed by
`sas-validation workloads list`. Each holds a `workload-definitions.workload-definition-specs`
list. Name them `<name>-wrkld-def.yaml`. Each workload's `scenario-config` and `path` are relative to the package's `scenarios/` directory
(for example `application-scenarios/sas-studio/scenario-config.yaml`).

### What the CLI checks after install

`sas-validation plugins validate` runs all of the checks below and reports every problem;
`sas-validation plugins list` loads each plugin and reports it as broken, with the reason, if
the manifest is invalid. `scenarios list` loads every scenario and checks:

- `release-manifest.yaml` exists and is a valid mapping.
- Every manifest scenario directory exists.
- The scenario config exists, and its `id` matches the manifest.
- Every entrypoint, workload definition, and required resource it names exists.
- Every `plugin-common` dependency is a safe relative path to a file that exists in the package.

### Building the archive

Run from the directory that **contains** the package directory, so the directory name becomes the
single top-level entry:

```bash
NAME=sas-validation-scenarios-platform
VERSION=2026.09

# COPYFILE_DISABLE stops macOS tar from adding ._* metadata files. GNU tar
# (`brew install gnu-tar`, run as `gtar`) is a good alternative on macOS.
COPYFILE_DISABLE=1 tar -czf "$NAME-$VERSION.tar.gz" \
  --exclude='.DS_Store' --exclude='__pycache__' --exclude='.git' \
  "$NAME-$VERSION"

shasum -a 256 "$NAME-$VERSION.tar.gz" > "$NAME-$VERSION.tar.gz.sha256"
```

Check it before publishing:

```bash
tar -tzf "$NAME-$VERSION.tar.gz" | head -5                       # one top-level directory
tar -tvzf "$NAME-$VERSION.tar.gz" | grep -E '^l|^h|\._|\.\./' || echo "clean"   # no links or junk
mkdir -p /tmp/pkg-check && tar -xzf "$NAME-$VERSION.tar.gz" -C /tmp/pkg-check
sas-validation --config /dev/null plugins validate --destination /tmp/pkg-check
sas-validation scenarios list --destination /tmp/pkg-check
```

`plugins validate` should report `PASS` for the plugin, and `scenarios list` should show every scenario with no errors.

### Publishing

**GitHub:**

```bash
gh release create "v$VERSION" "$NAME-$VERSION.tar.gz" "$NAME-$VERSION.tar.gz.sha256" \
  --title "Scenario package $VERSION" --notes-file RELEASE-NOTES.md
```

**GitLab:** create the release, then attach the archive as a release asset link.

```bash
glab release create "v$VERSION" \
  --name "Scenario package $VERSION" --notes-file RELEASE-NOTES.md

glab release upload "v$VERSION" \
  "$NAME-$VERSION.tar.gz" "$NAME-$VERSION.tar.gz.sha256"
```

`glab release upload` adds each file to the release as an asset link. You can also create the
release in one step with `--assets-links` and a JSON list of `{name, url}` entries. To store the
files in the project's Generic Package Registry instead of attaching them to the release directly,
add `--use-package-registry` to `glab release create`.

Publishing requires a token with the **`api`** scope and at least the **Developer** role on the
project. This is a higher bar than installing, which needs only `read_api`:

```bash
glab auth login --hostname gitlab.example.com
```

**Platform scenarios repository.** The platform scenarios repository automates these steps.
Do not create the tag yourself. Set `version` in `release-manifest.yaml` (quoted) and add a
`CHANGELOG.md` section, validate, push the cadence branch, then run:

```bash
python3 tools/validate_package.py --tag v2026.09.1
tools/release_gitlab.sh 2026.09.1 --dry-run     # check everything first
tools/release_gitlab.sh 2026.09.1               # build, tag, upload, create the release
```

The script builds the archive and checksum, creates tag `v<version>` on the pushed commit, uploads both
files to the Generic Package Registry, and creates the GitLab release with the `CHANGELOG.md`
section as notes. Its `README.md` has the full procedure, including mirroring to GitHub.

Then confirm users can see and install it:

```bash
sas-validation plugins list-repo-plugins --repo <alias>  # the tag and the .tar.gz asset are listed
sas-validation plugins install --repo <alias> --version "v$VERSION" --destination /tmp/pkg-install
```

### Notes

- **Checksums are not verified.** The `.sha256` file is published for humans and external
  tooling. `plugins install` does not check it today.
- **Fix, don't replace.** Published tags should be immutable. A re-uploaded archive under the
  same tag silently changes what users get, and machines that already installed the tag keep the
  old content until they uninstall and reinstall. Publish a patch version instead (`2026.09.1`).
- **Size.** Large data files belong in `resources/`. Remember GitHub and GitLab limit release
  asset sizes, so check your instance's limit before including large datasets.
