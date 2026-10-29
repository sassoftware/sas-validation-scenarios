# WHAT'S NEW ?!?

## 2026.10 (BREAKING CHANGES)
<details>
  <summary> Scenario packages and releases are now plugins</summary>

The `packages` and `releases` command groups were replaced by a single `plugins` group, following the
SAS Viya CLI `plugins` convention. Installed plugins were formerly *packages*; repository plugins
were formerly *releases*.

| Before | Now |
|--------|-----|
| `releases list [--repository <alias>]` | `plugins list-repo-plugins [--repo <alias>]` (all repositories by default, with `*`/`^` status markers) |
| `packages install --repository <alias> --version <v>` | `plugins install --repo <alias> --version <v>` |
| `packages list` | `plugins list` |
| | `plugins list-repos`, `plugins validate`, `plugins uninstall` (new) |
| `--package-version` (`run`, `workloads list`, `scenarios list`) | `--plugin-version`, plus a new `--repo` filter |
| `auth status --repository <alias>` | `auth status --repo <alias>` |
| `sas-validation.installed-packages.destination` | `sas-validation.installed-plugins.destination` (old key still accepted) |

Plugins are identified by repository alias and version, and now install into
`<destination>/<repository-alias>/<plugin>-<version>/` with an install record. Previously installed
plugins are still found. See [CLI-CHEATSHEET.md](./CLI-CHEATSHEET.md).
</details>

## 2026.05 


## 2026.04 (BREAKING CHANGES)
<details>
  <summary> Upgrade to Locust kubernetes operator 2.2.3</summary>

This is a BREAKING CHANGE update and will require you to re-install the new version of the locust operator using the new instructions provided.

This version of locust operator has the ability to mount shared PVC storage to the locust pods/containers so that locust can directly write output files (logs, sas-viya-cli output etc) directly to this mount. The /data is available as a mount point on all locust master and worker pods. 

With this change the custom resource spec template has changed as well. 
And in addition a locust_pvc.yaml file has been added to create the pvc to mount this location. 

</details>

<details>
  <summary> Insurance Capital Management (ICM) scenario added </summary>
A new solution scenario that targets sas-viya batch cli has been added in this release. For more details refer to the [ICM_Readme.md](./validation-scenarios/scenarios/solution-scenarios/sas-insurance-cap-mgt/ICM_Readme.md))
</details>

