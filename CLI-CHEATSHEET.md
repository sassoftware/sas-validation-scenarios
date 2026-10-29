# SAS Validation CLI Cheatsheet

Run commands from the `sas-validation-scenarios` repository root.

## Install the CLI on Linux or macOS

Clone the repository and change to that directory:
```bash
git clone <repository-url> sas-validation-scenarios
cd sas-validation-scenarios
```

Create and activate a virtual environment, then install the CLI and its Python packages:
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```
Set your kubernetes configuration file location:

```bash
export KUBECONFIG=~/.kube/configs/my-k8s.config
```

Create `sas-validation.yaml` from the template:
```bash
cp sas-validation.yaml.template sas-validation.yaml
```

Edit `sas-validation.yaml` and set `hostname` to your SAS Viya URL and `namespace` to the
Kubernetes namespace the workloads run in (the template uses `testing`):
```yaml
  execution:
    hostname: https://my-viya-system.example.com
    namespace: testing
```

Run the `preflight` check to ensure your environment is ready to run a scenario:
```bash
sas-validation preflight
```

If `preflight` finds issues, it can fix the ones that can be automated:
```bash
sas-validation preflight --fix
```

Install the default platform scenarios plugin (the leading `v` of the release tag is optional):
```bash
sas-validation plugins install --version v2026.08
```

Load your test users into a Kubernetes secret. Use the same namespace as `execution.namespace`:
```bash
sas-validation users load --users-file ./users.csv --namespace testing
```

The users file is a CSV file with one `user,password` row per user. For example:
```text
testUser1,a-secure-password
testUser2,a-secure-password
testUser3,a-secure-password
```

Run a simple Hello World to ensure your environment is set up correctly:
```bash
sas-validation run --workload helloviya-simple --plugin-version 2026.08

sas-validation run --scenario helloviya-simple --test tests/logonoff.py --users 1 --plugin-version 2026.08
```


### Activate the environment in a later session

Creating the environment and installing the CLI are one-time steps. After closing the
terminal, open a new terminal, change to the repository root, and activate the existing
`.venv` before running `sas-validation`.

On macOS or Linux:

```bash
cd /path/to/sas-validation-scenarios
source .venv/bin/activate
```

You do not need to recreate the environment or reinstall the CLI. To leave the environment,
run `deactivate`.

The active environment is shown by `(.venv)` at the start of your shell prompt.

The CLI automatically discovers these files in the current directory or the nearest
parent directory that contains them, so commands also work from subdirectories such as
`generated-workloads/`:

- `sas-validation.yaml` for framework, installed plugin, output, and execution defaults
- `scenario-repositories.yaml` for plugin repository aliases (the copy next to
  `sas-validation.yaml` is preferred)

Override either location with global options placed before the command:

```bash
sas-validation --config ./sas-validation.yaml \
    --repositories ./scenario-repositories.yaml <command>
```

Use `sas-validation --help` or `sas-validation <command> --help` for the complete
option list.

## Plugins: finding, installing, and managing Validation Scenarios

Validation scenarios are delivered as **plugins**. A plugin that is available in a configured
repository is a *repository plugin*; once installed it is an *installed plugin*. All plugin work
goes through one command group, modeled on the SAS Viya CLI `plugins` commands:

| Command | Purpose |
|---------|---------|
| `plugins list-repos` | List the configured plugin repositories |
| `plugins list-repo-plugins` | List plugins available in the repositories and whether they are installed |
| `plugins install` | Install a plugin version from a repository |
| `plugins list` | List installed plugins |
| `plugins validate` | Check installed plugins for missing or invalid content |
| `plugins uninstall` | Remove an installed plugin |

List the configured repositories. The default repository is marked `(default)`:

```bash
sas-validation plugins list-repos
```

Repositories are configured in `scenario-repositories.yaml`. The file in your copy of the
repository may differ from this example; `plugins list-repos` shows what is configured:
```yaml
# Default repository for plugins install and plugins uninstall when --repo is omitted.
# Override it per command with --repo <alias>.
default-repository: platform-scenarios

# Repository aliases used by the sas-validation plugins commands.
scenario-repositories:
  # Plugins containing platform-specific validation scenarios
  platform-scenarios:
    provider: github-release
    repository: my-org/my-scenarios-project
    visibility: public
```

List the plugins available in every configured repository, or in one with `--repo`:

```bash
sas-validation plugins list-repo-plugins
sas-validation plugins list-repo-plugins --repo <repository-alias>
sas-validation plugins list-repo-plugins --json
```

Each plugin version is prefixed with its status:

| Marker | Meaning |
|--------|---------|
| `*` | Installed locally and current |
| `^` | Installed locally, but the repository has a newer patch for the same cadence (for example `2026.09` installed, `2026.09.1` available) |
| (blank) | Available in the repository but not installed |

```text
Repository: platform-scenarios (github-release my-org/my-scenarios-project)
  2026.09.1  Scenario package 2026.09.1  published 2026-10-20 14:58:29 EDT
    url: https://github.com/my-org/my-scenarios-project/releases/tag/v2026.09.1
    assets: my-scenarios-project-2026.09.1.tar.gz
^ 2026.09  Scenario package 2026.09  published 2026-09-21 14:51:06 EDT
    ...

Status: * installed and current   ^ installed, newer version in repository   (blank) available, not installed
```

The published date is shown in your local time zone. `--json` output keeps the original UTC
`published-at` value from the repository.

If one repository cannot be reached (for example a missing GitLab token), its error is shown under
its heading, the other repositories are still listed, and the command exits with code 2.

### Install a plugin

A plugin is identified by its **repository alias and version**. Several repositories can publish a
plugin for the same SAS Viya cadence, so `--repo` says which one you mean. When `--repo` is omitted,
`default-repository` from `scenario-repositories.yaml` is used and the output names the repository:

```bash
sas-validation plugins install --version <version>
sas-validation plugins install --repo <repository-alias> --version <version>
```

Optional installation options:

```bash
sas-validation plugins install --repo <repository-alias> --version <version> \
    --destination <directory> --json
```

Plugins install into `<destination>/<repository-alias>/<plugin>-<version>/`, so plugins from
different repositories never collide. Each installed plugin records where it came from in a
`.sas-validation-plugin.yaml` file (repository alias, tag, asset, and install time). Installing a
version that is already installed from the same repository is rejected; uninstall it first.

For GitLab plugin repositories the CLI finds an access token automatically, in this order:

1. The `SAS_VALIDATION_RELEASE_TOKEN` environment variable
2. The GitLab CLI login (`glab auth login --hostname <host>`)
3. The git credential helper for the repository host

If you have none of these, log in once with the GitLab CLI (the token needs the `read_api`
scope), then check which source the CLI will use:

```bash
glab auth login --hostname <gitlab-host>
sas-validation auth status --repo <repository-alias>   # names the source; never prints the token
```

See [documentation/SCENARIO-REPOSITORIES.md](documentation/SCENARIO-REPOSITORIES.md) for how to
add repositories and the specification for publishing a plugin.

### List, validate, and uninstall installed plugins

```bash
sas-validation plugins list
sas-validation plugins list <plugin-path>
sas-validation plugins list --repo <repository-alias>
sas-validation plugins list --plugin-version <version>
sas-validation plugins list --destination <directory>
```

`plugins list` shows each plugin's name, version, source repository, Viya cadence, and its
scenario and workload counts. `--json` produces machine-readable output.

Check installed plugins for a valid manifest, scenario directories and configs, test
entrypoints, workload definitions, and required resources. The command exits with code 1 if
any plugin fails:

```bash
sas-validation plugins validate
sas-validation plugins validate <plugin-path>
sas-validation plugins validate --repo <repository-alias> --plugin-version <version> --json
```

Remove an installed plugin by repository and version (`--repo` defaults to `default-repository`),
or by its path. You are asked to confirm unless you pass `--yes`:

```bash
sas-validation plugins uninstall --repo <repository-alias> --version <version>
sas-validation plugins uninstall <plugin-path> --yes
```

Plugins installed before install records existed are matched by the `repository` field of their
`release-manifest.yaml`.

## Discover installed content

```bash
sas-validation workloads list
sas-validation scenarios list
sas-validation workloads list --scenario <scenario-id>
sas-validation workloads list --copy <workload> --plugin-version <version>
sas-validation workloads list --json
```

Scenario listings include the individual manifest-declared test entrypoints. Use `--json` to
consume them programmatically; each scenario has a `tests` array containing paths relative to
the scenario directory.

Both commands accept the same narrowing options as `plugins list`: an optional positional
`<plugin-path>`, `--repo <repository-alias>`, `--plugin-version <version>`, and
`--destination <directory>`.

Use `--copy <workload>` to copy a shipped workload definition into the configured
`sas-validation.custom-workloads.location`. Add `--overwrite` only when replacing
an existing customized copy intentionally.

## Check the environment

```bash
sas-validation preflight
sas-validation preflight --group cluster
sas-validation preflight --group client --group cluster
sas-validation preflight --fix --yes --users-file ./users.csv
sas-validation preflight --json
```

`--group` is repeatable and accepts `client` or `cluster`. `--fix` applies
automatable remediations; use `--yes` to skip its confirmation prompt. Add
`--namespace`, `--hostname`, `--framework-root`, or `--timeout <seconds>` to
override values used during inspection.

Load test users into the Kubernetes secret separately when needed:

```bash
sas-validation users load --namespace <namespace> --users-file ./users.csv
```

`users load` also accepts `--json`. It uses `KUBECONFIG` to reach the cluster.

## Generate and run

```bash
sas-validation run --workload <workload> --plugin-version <version>
sas-validation run --generate-only --workload <workload> --plugin-version <version>
sas-validation run --custom-workload <workload-file> --plugin-version <version>
sas-validation run --workload <workload> --repo <repository-alias> --plugin-version <version>
```

`-w`/`--workload` accepts a plugin workload name, definition filename, or
external definition path. `--workload-definition` remains available as a compatibility
alias. `--custom-workload` accepts a local workload file path directly, or a name
resolved from the configured custom workload directory. `--plugin-version` and
`--repo` are optional; use them to select among installed plugins when more than one
provides the workload or scenario (for example the same cadence installed from two
repositories). See the restricted-environment workflow
below for running staged local content.

`run` prepares, generates, and executes the workload in one step. Use
`--generate-only` to stop after generation without executing it.

Optional run overrides include:

```bash
sas-validation run -w <workload> --plugin-version <version> \
    --framework-root <directory> \
    --output <directory> \
    --users-file ./users.csv \
    --workload-overrides <file> \
    --log-level DEBUG
```

`--framework-root` and `--output` can instead come from `sas-validation.yaml`.
The configured `execution.hostname` is required for running or generating a
workload.

### Generated output layout

Each generation writes to `<output>/generated/`. Any earlier `generated/` folder is first renamed
to `generated-<timestamp>`.

```text
generated/
  runAllCreateWorkloadArtifacts.sh   # runs every workload's build/runCreateWorkloadArtifacts.sh
  <workload>/
    <workload>.yaml                  # resolved workload definition
    runWorkload.sh                   # executes the workload (what `run` calls)
    deployTaskResourcesAsConfigMap.sh
    execution-logs/  results/        # created by runWorkload.sh
    build/                           # generation-time scripts, setVariables.sh, logs/
    resources/                       # k8s-cr-*.yaml, users.csv, config.json, trustedcerts.pem
```

Workloads generated before this layout kept these files under `<workload>/artifacts/`. `run`
still finds `artifacts/runWorkload.sh` in those older folders.

> `resolve`, `prepare`, and `generate` are not registered commands, and there is no top-level
> `validate` (use `plugins validate` to check installed plugins). Use `run --generate-only` when generation without execution is needed.

## Restricted or air-gapped environments

The CLI can run plugin content transferred from a network-permitted staging
environment. It resolves the plugin and workload from local paths without
querying a public repository or release service. Plugin-specific generation
scripts may have additional network requirements.

1. In the staging environment, retrieve the plugin using the install
   command and a destination directory:

   ```bash
   sas-validation plugins install --repo <repository-alias> --version <version> --destination <directory>
   ```

2. Scan and approve the plugin and custom workload definition according to
   your organization's transfer process. Transfer the unpacked plugin
   directory (`<directory>/<repository-alias>/<plugin>-<version>`), workload YAML file, framework files, and `sas-validation.yaml`
   into the cluster-connected environment. Ensure the CLI and its Python
   dependencies are already installed there using an approved process.
3. In the target configuration, set `framework-root`, `output.destination`,
   and the HTTPS `execution.hostname`. The target environment must be able to
   reach Viya. A direct workload file path does not require
   `custom-workloads.location`; that setting is needed when selecting a
   workload by name.
4. Run the staged workload with the local plugin directory and workload file:

   ```bash
   sas-validation run <plugin-path> --custom-workload <local-workload-file>
   ```

`<plugin-path>` must be the unpacked plugin directory; the CLI does not import
local plugin archives. `--plugin-version` and `--repo` are ignored when a plugin path
is supplied. `run` generates and executes the workload, so `--generate-only`
does not replace Viya connectivity, and plugin generation scripts may have
additional environment requirements.


