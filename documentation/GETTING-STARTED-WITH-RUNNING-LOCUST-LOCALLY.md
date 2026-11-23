# Running Validation Scenarios Outside of Kubernetes

`sas-validation run --local` runs a workload with Locust on your own machine (a laptop or a VM)
instead of deploying it to Kubernetes. It uses the same plugins, workload definitions, and
results layout as a Kubernetes run, so a scenario that passes locally runs unchanged in the
cluster. No Kubernetes cluster, namespace, operator, or `KUBECONFIG` is needed.

Local runs are a good fit for single-user checks, scenario development, and debugging. Use
Kubernetes for load tests with many users.

## Before you start

- **Machine.** macOS or Linux with Python 3.9 or later and `bash`; Python 3.10 or later is
  recommended. On Python 3.9, Locust's `gevent` dependency has no prebuilt package for some
  platforms (for example Linux on ARM), so pip must compile it, which needs a C compiler and the
  Python development headers. Locust's `--processes` option
  is not supported on Windows. Each simulated user runs a Chromium browser, so size the machine
  for the users you run: on a VM with 8 CPUs, 2 or 3 users typically give better results than 10.
- **Network.** The machine can reach your SAS Viya URL.
- **SAS Viya.**
  - The welcome screen and new user tour are disabled.
  - SAS Studio is installed and compute nodes are available. A manual sign-in to SAS Studio as a
    test user starts a compute server.
  - The test users exist in SAS Viya and are **not** administrators.
  - **Very important:** the content the scenarios need is loaded. See
    [RESOURCES-SETUP.md](./RESOURCES-SETUP.md).

## Set up the CLI

Install the CLI with the `local` extra, which adds Locust, locust-plugins, Playwright, and
python-dotenv:

```bash
cd sas-validation-scenarios
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --prefer-binary -e '.[local]'
```

`--prefer-binary` lets pip choose an older release with a prebuilt package over a newer one that
would have to be compiled.

If you skip the extra, `run --local` finds the missing packages before it generates anything and
offers to install them (see [Missing dependencies](#missing-dependencies)).

Create `sas-validation.yaml` from its template and set the SAS Viya URL. Set `trusted-certs` too
if your Viya system uses a certificate that this machine does not trust:

```bash
cp sas-validation.yaml.template sas-validation.yaml
```

```yaml
  execution:
    hostname: https://my-viya-system.example.com
    users-file: users.csv           # optional; --users-file overrides it
    # trusted-certs: trustedcerts.pem
```

`namespace` is not used by local runs.

## Create the users file

Local runs read test credentials from a CSV file with one `user,password` row per user; they never
read the Kubernetes secret. Name the file with `--users-file` or with `execution.users-file`:

```text
user1,pass1
user2,pass2
user3,pass3
```

Provide at least as many users as the workload runs concurrently.

## Check the machine

```bash
sas-validation preflight --group local
sas-validation preflight --group local --fix
```

The `local` group checks the Python version (it warns below 3.10), that the Locust and Playwright
modules and the Playwright Chromium browser
are installed, that the users file can be read, and that SAS Viya answers at `/SASLogon/login`.
`--fix` installs missing modules with `pip` and runs `playwright install chromium`. On Linux the
browser may also need system libraries:
`sudo python3 -m playwright install-deps chromium`. If the check reports that the Playwright driver
cannot start because a system library is missing, install that library first; see
[TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

The `local` group runs only when you ask for it. A plain `sas-validation preflight` still checks
the `client` and `cluster` groups.

## Run a workload

Use any selector that `run` accepts, and add `--local`:

```bash
# A single test from a scenario, with one user
sas-validation run --local --scenario helloviya-simple --test tests/logonoff.py --users 1

# An authored workload from an installed plugin
sas-validation run --local --workload helloviya-simple --plugin-version 2026.09

# A customized workload, with an explicit users file
sas-validation run --local --custom-workload my-workload --users-file ./users.csv

# Generate the local artifacts without running them
sas-validation run --local --workload helloviya-simple --generate-only
```

Each workload in the definition runs as its own Locust test, with the users, spawn rate,
iterations, run time, and timeout from the workload definition (and `--workload-overrides`).
Locust runs in its own headless mode, without the Locust web UI.

### Options for local runs

| Option | Effect |
|--------|--------|
| `--local` | Run Locust on this machine instead of Kubernetes. |
| `--headed` | Show the Playwright browser windows. The default is headless. |
| `--processes <n>` | Number of Locust worker processes. The default is the workload's user count, so each user gets its own process (like one worker pod per user in Kubernetes). |
| `--users-file <file>` | Users CSV; overrides `execution.users-file`. |
| `--yes` | Install missing Locust/Playwright dependencies without asking. |

### Missing dependencies

Before it generates the workload, `run --local` checks that the Locust and Playwright packages
and the Playwright Chromium browser are installed for the Python that runs `sas-validation`. If any
are missing, it lists them and asks whether to install them (`[y/N]`). Answering `y` (or passing `--yes`)
runs the same fixes as `sas-validation preflight --group local --fix`. Answering `n`, or a failed
install, stops the run with exit code 2. `--generate-only` skips the check.

The generated script runs the `locust` installed for that same Python, even when it is not on
`PATH`. Set `SAS_VALIDATION_LOCUST` to the path of another `locust` executable to use a different
one.

### Headed or headless browsers

- **Headless** (default): the browsers run in the background.
- **Headed** (`--headed`): a browser window opens for every user so you can watch the test. Use
  it with 1 to 3 users; the CLI warns when a headed run has more.

The generated script can also be switched when you run it:
`SAS_VALIDATION_HEADLESS=false ./runWorkloadLocal.sh`.

## Stopping runs and recovering leftover processes

Press **Ctrl+C** once to stop a run. Newly generated local runners supervise Locust in an
isolated process group and track descendant identities. On completion, failure, timeout, or
interruption, they stop remaining owned processes, allowing up to 15 seconds for graceful
shutdown before force-stopping them. This applies to headed and headless runs, including
direct execution of the generated script. Logs and collected results are preserved.

Each Locust invocation prints `local_run_id=<id>` in its live workload log. Ownership records
are kept in the current user's platform-specific application state directory, outside the
generated workload and rotating logs. Inspect them after an abnormal termination:

```bash
sas-validation cleanup --local --list
sas-validation cleanup --local --run-id <id>          # preview only
sas-validation cleanup --local --run-id <id> --stop   # asks for confirmation
```

Add `--yes` with `--stop` for non-interactive cleanup. Cleanup validates PID, process creation
time, user, and process group before signaling; it does not search by executable name or stop
other local runs. A stale record with no matching processes is removed when cleanup is requested.
An interrupted run stops rather than proceeding to the next workload.

`SIGKILL` cannot execute shutdown handlers. Persisted identities allow recovery of recorded
survivors after the supervisor is killed. Processes that detach and lose their parent before
being observed cannot be reliably attributed; neither can leftovers from older generated
scripts or Locust launched by hand. Regenerate existing workloads to enable supervision.
Avoid blanket commands targeting all Python, Node.js, or Chromium processes.

## Results

The run prints a summary and exits with code 0 when every workload passes, 1 when a workload
fails, and 2 when the environment is not ready (for example, Locust is not installed). A workload
fails when Locust reports more than 1% failed requests, when the failures or exceptions results
have rows, when the Locust output contains errors, or when it does not finish within the workload
timeout.

```text
generated/
  <workload>/
    <workload>.yaml              # resolved workload definition
    runWorkloadLocal.sh          # runs Locust for every workload in the definition
    local/src/                   # test files, common libraries, users.csv, config.json, trustedcerts.pem
    results/<users>-<name>.csv   # Locust statistics
    execution-logs/              # <name>-locust.log, failures and exceptions CSVs, run log
```

`runWorkloadLocal.sh` can be run again without regenerating. Earlier `execution-logs` folders are
kept as `execution-logs-<timestamp>`.

To run Locust by hand, change to `local/src` and point the users loader at the staged file.
This bypasses the generated runner's automatic cleanup and ownership tracking:

```bash
cd generated/<workload>/local/src
SAS_VALIDATION_USERS_FILE=$PWD/users.csv SAS_VALIDATION_HEADLESS=false \
  locust -f logonoff.py -H https://my-viya-system.example.com --headless \
  -u 1 -r 1 --processes 1 --iterations 1 --only-summary
```

For more Locust options, see the
[Locust command-line documentation](https://docs.locust.io/en/stable/configuration.html).

## Scenarios that need Kubernetes

Some tests depend on the Locust pod, for example paths under `/lotest/src` or tools installed in
the Locust image. A scenario marks this in its `scenario-config.yaml`, and `run --local` refuses it
with a clear message:

```yaml
scenario-config:
  id: sas-viya-cli
  execution-targets: [kubernetes]   # kubernetes, local, or both; omitted means both
```
