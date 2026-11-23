# Troubleshooting
This page is designed to help users identify, diagnose, and resolve problems relating to the usage of SAS Validation Scenarios. 

## Problem: Unable to access viya url

### Overview
When running validation scenarios, we have noticed situations where the locust master and worker pods are unable to access the viya url. 
We have noticed these in eks clusters and also when unning the validation scenarios in one cluster and Viya in another.
When you run the tests, you would get error messages about not being able to connect to the supplied URL, and eventually would get a load timeout error in the stats_failures file on the master pod.

```
event,01: Navigate to SASLogon,"CatchResponseError('Page.goto: Timeout 60000ms exceeded.Call log:  - navigating to ""https://myviya.domain.org/SASLogon"", waiting until ""load""')",5

OR

TASK,logonoff.test_logonoff,CatchResponseError('Page.screenshot: Timeout 60000ms exceeded.Call log:  - taking page screenshot  -   - waiting for fonts to load...  -   - fonts loadedabout:blank'),1
```

When the locust pods (master and workers) are running Kubernetes, they try to access the web site via the external hostname 
(ex. https://yourviya.domain.org).
As is normally the case in this situation in kubernetes, the public ip address of the pods 
need to be added to the NGINX Ingress service definition.
All pods that access the outside world get the same public ip address, the one that is associated with the NAT Gateway for that subnet.
You always need the public ip addresses in the loadBalancerSourceRanges list.

### How to debug

Exec into the locust master pod. There was no curl, wget, etc. in that container.  However, there was python and python3.

Run this code in python (in the master pod container) to retrieve the public ip address:

```
   import requests   
   response = requests.get('https://ifconfig.me')
   print(f"Content: {response.content}")
```

You will see what the public ip address is of the pod in the printf of the response content.
This ip address needs to be added to the loadBalancerSourceRanges of the NGINX service definition.

In AWS, you will also need the NAT gateway definitions for the VPC and get their Public IP addresses associated with them
You will alos need to add this ipaddress to the loadBalancerSourceRanges of the NGINX service definition.

### Solution

`kubectl edit service ingress-nginx-controller -n ingress-nginx`

Add both the public ip address to the loadBalancerSourceRanges as x.x.x.x/32

## Problem: `Failed building wheel for gevent` when installing the local extras

### Overview

`sas-validation run --local`, `sas-validation preflight --group local --fix`, or
`pip install -e '.[local]'` fails with a message such as:

```text
pip could not build gevent from source (no prebuilt package for Python 3.9 on aarch64); use Python 3.10 or newer
```

or, in pip's own output, `ERROR: Failed building wheel for gevent`.

### Root Cause

Locust depends on `gevent`, a compiled package. When the Python version and platform have no
prebuilt package (for example Python 3.9 on Linux ARM), pip downloads the source and compiles it,
which fails without a C compiler and the Python development headers. `sas-validation preflight
--group local` reports Python versions older than 3.10 as a warning.

### Solution

- Use Python 3.10 or later for the virtual environment that runs `sas-validation`, then install
  again with `python3 -m pip install --prefer-binary -e '.[local]'`.
- Or, to stay on the current Python, make a C compiler and the Python development headers
  available so pip can build `gevent`.

The full pip output is saved to the log file named in the error message.

## Problem: the Playwright driver cannot start (`error while loading shared libraries`)

### Overview

`sas-validation preflight --group local` or `run --local` reports:

```text
the Playwright driver cannot start: the system library libatomic.so.1 is missing
```

### Root Cause

Playwright runs a bundled Node.js driver for every command, including `playwright install` and
`playwright install-deps`. On minimal Linux systems a shared library that Node.js needs can be
missing, so none of these commands can start and `--fix` cannot install the browser.

### Solution

Install the system package that provides the named library with the system's package manager,
then run `python3 -m playwright install chromium` (or `sas-validation preflight --group local --fix`).
If Chromium then fails to start, it also needs its own system libraries; on Debian and Ubuntu
`sudo python3 -m playwright install-deps chromium` installs them.

## Problem: Local headed runs leave workers or browser processes behind

Newly generated local runners automatically stop run-owned Locust workers and browser
descendants on exit, with a 15-second grace period. Press Ctrl+C once and allow cleanup to finish.
After a forced termination, inspect tracked processes and stop only the affected run:

```bash
sas-validation cleanup --local --list
sas-validation cleanup --local --run-id <id>
sas-validation cleanup --local --run-id <id> --stop
```

The second command is a preview; the third requests confirmation. Do not terminate all
Python, Node.js, or Chromium processes by name. Older generated scripts and manually started
Locust processes have no ownership records; regenerate workloads to enable tracking.
See [recovery details and limitations](GETTING-STARTED-WITH-RUNNING-LOCUST-LOCALLY.md#stopping-runs-and-recovering-leftover-processes).

## Problem: A `tee` process remains after generation or a workload run

Older generated Kubernetes runners restored stdout and stderr without waiting for their
`tee` log writer, which could leave a live process or a zombie behind. Artifact generation
and both local and Kubernetes runners now close the logging pipe, allow up to two seconds
for the writer to finish, and stop and reap it if necessary. The original exit status is
preserved on success, failure, and interruption.

Regenerate workloads after updating the framework so copied build scripts and generated
runners include these fixes. This also applies to runs without `--local`; the local run
registry does not track log writers orphaned by older scripts.
For an existing leftover, inspect `ps -o pid,ppid,stat,args -p <pid>` first:
only terminate that specific PID if it is still an active log writer belonging to a finished
run. A process marked `Z` is already dead and must be reaped by its parent; killing it again
does not help. Containers should use an init process (for example Docker's `--init`) to reap
orphans, but that is not a substitute for the framework waiting for its own children.

## Problem: AWS Authentication Saturation with EKS kubeconfig During Locust Scaling

### Overview

Issue encountered when deploying large numbers of Kubernetes workers (for example, 200 Locust workers) using a standard AWS-generated kubeconfig.
The standard kubeconfig generated using 'aws eks update-kubeconfig' contains an exec authentication block that runs 'aws eks get-token' whenever authentication is required. When many Locust workers start simultaneously, each worker independently triggers AWS token generation. This results in a surge of AWS STS authentication calls.
Observed impacts include:
· AWS API throttling and authentication saturation
· Slower Kubernetes worker deployment times
· Increased infrastructure overhead unrelated to workload testing
· Reduced reliability during large-scale deployments

### Root Cause
The default kubeconfig dynamically retrieves authentication tokens using AWS CLI exec calls. This works well for interactive use but does not scale efficiently when hundreds of parallel workers request authentication simultaneously.

### Proposed Solution

Generate a static kubeconfig file that contains a pre-generated temporary Kubernetes token. This removes the runtime dependency on AWS authentication for each worker and significantly reduces the number of AWS API calls during deployment.
Benefits of the Static Token Approach
· Eliminates large bursts of AWS authentication calls
· Improves deployment speed and reliability
· Reduces risk of AWS throttling
· Provides more stable high-scale Locust deployments

### Considerations
The static token is temporary and must be regenerated periodically.
For long-running tests, generate a new static kubeconfig before the token expires.
