## Current CLI (Typer-based, 2026-10)

```
Usage: sas-validation [OPTIONS] COMMAND [ARGS]...

Commands:
  run          Generate a workload and run it
  preflight    Inspect the environment for everything a generated workload needs
  plugins      Install, list, and manage scenario plugins
  workloads    List workload definitions in installed plugins
  scenarios    List scenarios in installed plugins
  users        Manage the test users used by workloads
  auth         Check which access token is used for private plugin repositories
```

### Plugins

Validation scenarios are delivered as **plugins**, following the SAS Viya CLI `plugins`
convention. A plugin available in a configured repository is a *repository plugin*; once
installed it is an *installed plugin*. The former `packages` and `releases` command groups were
replaced by `plugins`.

```text
sas-validation plugins list-repos                  # configured repositories
sas-validation plugins list-repo-plugins           # plugins in every repository, with status
sas-validation plugins install --version <version> [--repo <alias>]
sas-validation plugins list                        # installed plugins
sas-validation plugins validate                    # check installed plugins
sas-validation plugins uninstall --version <version> [--repo <alias>] | <plugin-path>
```

A plugin is identified by **repository alias + version**, because several repositories can
publish a plugin for the same SAS Viya cadence. `install` and `uninstall` use
`default-repository` from `scenario-repositories.yaml` when `--repo` is omitted; if no default
is configured, `--repo` is required. Plugins install into
`<destination>/<repository-alias>/<plugin>-<version>/` with a `.sas-validation-plugin.yaml`
install record naming the source repository and tag.

`list-repo-plugins` queries every configured repository unless `--repo` is given, and prefixes
each version with its status: `*` installed and current, `^` installed but the repository has a
newer patch of the same cadence, blank available but not installed. The human-readable output
otherwise shows the version, release name, publication time, URL, and assets; `--json` adds
descriptions, timestamps, draft/pre-release flags, asset details, and `status`.

### Other resource commands

```text
sas-validation workloads list
sas-validation scenarios list
sas-validation users load
sas-validation auth status --repo <alias>   # which token source a private GitLab repository will use
```

`run`, `workloads list`, `scenarios list`, `plugins list`, and `plugins validate` accept
`--plugin-version <version>` and `--repo <alias>` to choose among installed plugins.

Workflow commands remain top-level because they describe an end-to-end operation:
`run` and `preflight`.

`resolve`, `prepare`, and `generate` from the argparse-era sketch were removed in the
Typer-based CLI redesign; `generate`'s behavior is folded into `run`. See
[CLI-CHEATSHEET.md](CLI-CHEATSHEET.md) for full usage.
