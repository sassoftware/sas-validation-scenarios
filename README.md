# SAS Validation Scenarios

## Overview
The **sas-validation-scenarios** repository contains a collection of tools and scripts designed to run automated tests against various SAS Viya 4 applications to verify functionality and performance.
These tests are fully self-contained and can be executed on any cloud platform and across any SAS Viya cadence.
They can be run as single-user tests or scaled to simulate load with multiple concurrent users.
The only requirement is access to a valid SAS Viya 4 web application.
Before getting started, review the following documents:

- [What are validation scenarios?](./documentation/INTRODUCTION.md)
- [Where and how to execute sas-valdiation-scenarios](./documentation/BEFORE-YOU-START.md)


# VERY IMPORTANT

Starting with the **version 2.0** branch of the sas-validation-scenarios, we have separated the reusable validation execution framework from the scenario content that it runs. This makes it possible to publish, update, and use scenario collections independently while keeping the execution experience consistent.

# Framework vs Scenarios

Earlier, the validation framework and the scenarios were bundled together. Keeping the framework and scenarios in one repo creates two main problems. 
- First, releases are coupled: a small scenario fix (like a CSV typo) needs a framework release, and a framework fix pulls in unrelated scenario changes. 
- Second, ownership is blurred: scenario authors, such as the Fraud or a Risk team, must work in the same repo as the team maintaining the execution engine.

Starting with the version 2.0 release, it splits them into two kinds of repositories:

- Framework: This is the engine. It knows how to create and execute workloads, gather and report results etc
- plugins: The Scenarios or usecases are now delivered as plugins. This is the content. They hold the tests, flows, data, and docs for a specific solution or use case.

An analogy is a test runner and a test suite. pytest is not bundled with your application’s tests. It’s a separate tool that discovers and runs them. Here, the framework plays the role of pytest, and each scenario collection plays the role of a test suite.

# Branching Plan

**sas-validation-scenarios:** 

Branches 2026.01 through 2026.07 remain on the legacy execution model. After that, development moves to a single "2.0" branch with no further viya cadence branches in this repository. 

**sas-validation-scenarios plugins:** 
The Scenarios or usecases are now delivered as plugins. These plugins will deliver cadence branches as and when they become available. 

Here are the available sas-validation-scenarios plugins repository


| plugin name | link | versions |
| ------ | ------ | ------|  
|    plaform    |   [sas-validation-scenarios-platform](https://github.com/sassoftware/sas-validation-scenarios-platform))     | Starting with 2026.08, these will be validated and updated for every viya cadence that is supported.
|     risk    |  [sas-validation-scenarios-risk](https://github.com/sassoftware/sas-validation-scenarios-risk)      | Will follow their own update cycle 
|     fraud   |  [sas-validation-scenarios-fraud ](https://github.com/sassoftware/sas-validation-scenarios-fraud)    | Will follow their own update cycle.

### What does plugin versions mean (--version)?
Each validation scenario plugin contains a scenario validated for a specific viya cadence. When new cadences are released, the scenarios are validated against them and published as new plugin versions.

# Getting Started

There are two parts to installing the sas-validation-scenarios:
- **sas-validation cli**: This part installs the framework and the cli pieces
- **sas-validation plugins**: This part installs the plugin pieces

You will need both to run the sas-validation-scenarios. 

## Installing the sas-validation CLI on Linux

Create and activate a virtual environment, then install the CLI from the repository root:

Clone the repository and change to that directory:

```bash
git clone https://github.com/sassoftware/sas-validation-scenarios.git sas-validation-scenarios
cd sas-validation-scenarios
#Checkout is only needed for Dev
git checkout sas-validation-cli
```


Install the required Python plugins:
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```
Note: Creating the environment and installing the CLI are one-time steps. 
If already installed, you will just need to  activate the existing .venv before running sas-validation.

```bash
cd /path/to/sas-validation-scenarios
source .venv/bin/activate
```

Set your kubernetes configuration file location:

```bash
export KUBECONFIG=/path/to/your/<kubeconfig>
```

Edit `sas-validation.yaml` and set `hostname` to your SAS Viya URL. Optionally, change `namespace` to deploy to a different Kubernetes namespace (the default is `validation-scenarios`):
```yaml
  execution:
    hostname: https://my-viya-system.example.com
	namespace: validation-scenarios
```

Run the `preflight` check to ensure your environment is ready to run a scenario
```bash
sas-validation preflight
```

If `preflight` find issues, it will offer to fix those it is able to
```bash
sas-validation preflight --fix
```
## viya users will be sourced from users.csv 

users will be sourced from a users.csv file residing in the root of this dir. 

There are two options to provide the user list to the workload: 
Load your test users to k8s secrets *(Assuming you are using the default namespace `validation-scenarios`)*
```bash
sas-validation users load --users-file ./users.csv --namespace validation-scenarios
```

Second option is to provide them at run time by using the following optiom:
--users-file users.csv

The format for the users file is user/password.  For example
```bash
testUser1,a-secure-password
testUser2,a-secure-password
testUser3,a-secure-password
```

# git repositories and access token 

SAS Validation Scenarios comes configured with a default set of repositories.  You can review them in `scenario-repositories.yaml`

```bash
# Default repository for plugins install and plugins uninstall when --repo is omitted.
# Override it per command with --repo <alias>.
default-repository: platform-scenarios

# Repository aliases used by the sas-validation plugins commands.
scenario-repositories:
  # Plugins containing platform-specific validation scenarios
  platform-scenarios:
    provider: github-release
    repository: sas-software/sas-validation-platform-scenarios
    visibility: public
```

Each of these plugin repos needs access.  For GitLab plugin repositories the CLI finds an access token automatically, in this order:

1. The `SAS_VALIDATION_RELEASE_TOKEN` environment variable
2. The GitLab CLI login (`glab auth login --hostname <host>`)
3. The git credential helper for the repository host

If you have none of these, log in once with the GitLab CLI (the token needs the `read_api`
scope), then check which source the CLI will use:

Alternatively, you can go to gitlab and create a token and export the token secret such as this:

```bash
export SAS_VALIDATION_RELEASE_TOKEN=<your token secret>
```

```bash
glab auth login --hostname <gitlab-host>
sas-validation auth status --repo <repository-alias>   # names the source; never prints the token
```


# Plugins: finding, installing, and managing Validation Scenarios

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


List the plugins available in every configured repository, or in one with `--repo`:

```bash
sas-validation plugins list-repo-plugins
sas-validation plugins list-repo-plugins --repo sas-fraud-solutions
sas-validation plugins list-repo-plugins --json
```

Each plugin version is prefixed with its status:

| Marker | Meaning |
|--------|---------|
| `*` | Installed locally and current |
| `^` | Installed locally, but the repository has a newer patch for the same cadence (for example `2026.09` installed, `2026.09.1` available) |
| (blank) | Available in the repository but not installed |

```text
Repository: platform-scenarios (github-release sas-software/sas-validation-platform-scenarios)
  2026.09.1  Scenario package 2026.09.1  published 2026-10-20T18:58:29Z
    url: https://github.com/.../releases/tag/2026.09.1
    assets: sas-validation-platform-scenarios-2026.09.1.tar.gz
^ 2026.09  Scenario package 2026.09  published 2026-09-21T18:51:06Z
    ...

Status: * installed and current   ^ installed, newer version in repository   (blank) available, not installed
```

If one repository cannot be reached (for example a missing GitLab token), its error is shown under
its heading, the other repositories are still listed, and the command exits with code 2.

### Install a plugin

A plugin is identified by its **repository alias and version**. Several repositories can publish a
plugin for the same SAS Viya cadence, so `--repo` says which one you mean. When `--repo` is omitted,
`default-repository` from `scenario-repositories.yaml` is used and the output names the repository:

Before you do the install, it would be a good idea to run the following commands to see what plugins are availabe:

```bash
$ sas-validation plugins list-repos
NAME                           PROVIDER        REPOSITORY                    VISIBILITY  BASE URL
my-gitlab-scenarios (default)  gitlab-release  my-group/my-scenarios-project  private     https://gitlab.example.com
private-scenarios              gitlab-release  my-group/my-scenarios-project  private     https://gitlab.example.com
```


```bash
$ sas-validation plugins list-repo-plugins
Repository: my-gitlab-scenarios (gitlab-release my-group/my-scenarios-project)
* 2026.08  Scenario package 2026.08  published 2026-10-20 12:02:06 PDT
    url: https://gitlab.example.com/my-group/my-scenarios-project/-/releases/v2026.08
    assets: sas-validation-scenarios-platform-2026.08.tar.gz.sha256, sas-validation-scenarios-platform-2026.08.tar.gz

Repository: private-scenarios (gitlab-release my-group/my-scenarios-project)
  2026.08  Scenario package 2026.08  published 2026-10-20 12:02:06 PDT
    url: https://gitlab.example.com/my-group/my-scenarios-project/-/releases/v2026.08
    assets: sas-validation-scenarios-platform-2026.08.tar.gz.sha256, sas-validation-scenarios-platform-2026.08.tar.gz

Status: * installed and current   ^ installed, newer version in repository   (blank) available, not installed
```

Now you can do an install with the information you have discovered above: 


```bash
# Since --repo is missing, it will install the default paltform repo 
sas-validation plugins install --version 2026.08 
# example where you specify a repo and a version 
sas-validation plugins install --repo <repository-alias> --version <version>
Eg: sas-validation plugins install --repo my-gitlab-scenarios --version 2026.08
```

Versions are written without the `v` (for example `2026.08`). Release tags carry a leading `v`
(`v2026.08`) so they do not clash with branches of the same name; the CLI accepts either form.

Optional installation options:

```bash
sas-validation plugins install --repo <repository-alias> --version <version> \
	--destination <directory> --json
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

# Workloads 

Each plugins is built on testcases. And testcases can be run as a workload. 


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

### Run locally, without Kubernetes

`run --local` runs the workload with Locust on this machine. Install the extra packages with
`pip install --prefer-binary -e '.[local]'` (Python 3.10 or later recommended), check the machine with `sas-validation preflight --group local --fix`,
and provide a users CSV with `--users-file` or `sas-validation.execution.users-file`. If the packages
or the Chromium browser are missing, `run --local` offers to install them before it generates
anything (`--yes` installs without asking):

```bash
sas-validation run --local --scenario helloviya-simple --test tests/logonoff.py --users 1 --users-file ./users.csv
sas-validation run --local --workload <workload> --plugin-version <version> [--headed] [--processes <n>]
```

A local generation writes `local/src/` (the test files and their dependencies) and
`runWorkloadLocal.sh` instead of the Kubernetes artifacts. See
[Running Validation Scenarios Outside of Kubernetes](documentation/GETTING-STARTED-WITH-RUNNING-LOCUST-LOCALLY.md).

> `resolve`, `prepare`, and `generate` are not registered commands, and there is no top-level
> `validate` (use `plugins validate` to check installed plugins). Use `run --generate-only` when generation without execution is needed.

 
## License
This project is licensed under the [Apache 2.0 License](LICENSE).

## Contributing
Maintainers are accepting patches and contributions to this project.
Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details about submitting contributions to this project.

## Third-Party Dependencies
This project uses the following direct open source dependencies declared in `pyproject.toml`.

| Dependency | Use | License |
| ---------- | --- | ------- |
| [setuptools](https://pypi.org/project/setuptools/) | Build system | [MIT](https://github.com/pypa/setuptools/blob/main/LICENSE) |
| [deepmerge](https://pypi.org/project/deepmerge/) | Runtime | [MIT](https://github.com/toumorokoshi/deepmerge/blob/master/LICENSE) |
| [kubernetes](https://pypi.org/project/kubernetes/) | Runtime | [Apache License 2.0](https://github.com/kubernetes-client/python/blob/master/LICENSE) |
| [platformdirs](https://pypi.org/project/platformdirs/) | Runtime | [MIT](https://github.com/tox-dev/platformdirs/blob/main/LICENSE) |
| [psutil](https://pypi.org/project/psutil/) | Runtime | [BSD 3-Clause](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| [PyYAML](https://pypi.org/project/PyYAML/) | Runtime | [MIT](https://github.com/yaml/pyyaml/blob/main/LICENSE) |
| [Typer](https://pypi.org/project/typer/) | Runtime | [MIT](https://github.com/fastapi/typer/blob/master/LICENSE) |
| [Locust](https://locust.io/) | Optional `local` extra | [MIT](https://github.com/locustio/locust/blob/master/LICENSE) |
| [Locust Plugins](https://github.com/SvenskaSpel/locust-plugins) | Optional `local` extra | [Apache License 2.0](https://github.com/SvenskaSpel/locust-plugins/blob/master/LICENSE) |
| [Playwright](https://playwright.dev/python/) | Optional `local` extra | [Apache License 2.0](https://github.com/microsoft/playwright/blob/main/LICENSE) |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Optional `local` extra | [BSD 3-Clause](https://github.com/theskumar/python-dotenv/blob/main/LICENSE) |

This list covers direct dependencies; transitive dependencies are governed by their respective licenses.
