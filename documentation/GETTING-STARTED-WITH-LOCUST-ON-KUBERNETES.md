# Getting Started with Locust on Kubernetes

## Table of Contents
- [Overview](#Overview)
- [Preparing your client](#preparing-your-client)
- [Preparing the environment](#preparing-the-environment)
  - [Installing the Locust Kubernetes Operator](#installing-the-locust-kubernetes-operator)
  - [Configuring the Viya environment](#configuring-the-viya-environment)
  - [Optional: Creating a dedicated nodepool](#optional-creating-a-dedicated-nodepool)
  - [Defining Test Users](#defining-test-users)
- [Providing User Credentials](#providing-user-credentials)
- [Running Scenarios](#running-scenarios) 
     - [Single scenario example: helloviya-simple](#single-scenario-example-helloviya-simple)
     - [Single scenario example: helloviya-advanced](#single-scenario-example-helloviya-advanced)
     - [Mixed scenario example: mixed-studio-vf](#mixed-scenario-example-mixed-studio-vf)
- [Execution Logs](#execution-logs)
- [What to expect when you execute runWorkloads](#what-to-expect-when-you-execute-runworkloads)


## Overview

This section assumes that you have completed the necessary setup required to run a specific scenario.

This project leverages **Locust** and **Playwright** on **Kubernetes**, taking full advantage of cloud-native scalability.  
By design, the **[locust-k8s-operator](https://docs.locust.io/en/stable/kubernetes-operator.html)** can be deployed on any Kubernetes cluster, enabling you to create a fully distributed performance testing environment in seconds. 

The Locust Operator for Kubernetes is an operator that manages the lifecyle of Distributed load generation inside a Kubernetes cluster.
It is a Custom Resource Definition (CRD) and a Controller that run on your Kubernetes cluster and allow you to create and manage your Locust tests as Kubernetes resources. Automatically creates master/worker jobs, mounts locustfiles, exposes the web UI, collects metrics, and handles restarts when the spec changes.

This approach allows you to:

- Deploy a **cloud-native performance testing system** anywhere, on demand.
- **Auto-scale** test workloads up or down based on load demands.
- Utilize the **Locust master–worker architecture** to distribute load across multiple nodes.
- Simulate **real-world traffic** by generating concurrent users from multiple instances and regions.

The only limitation to this approach is the amount of cluster resources your team or organization allocates for performance testing.  
With Kubernetes’ native scaling capabilities, you can dynamically adjust the number of simulated users and workload intensity to model realistic, production-scale load scenarios.

## Preparing your client
The host on which you use this project to execute tests needs to have the following prerequisites configured:

  - kubectl installed with a valid kubeconfig file
  - python3 installed with the following modules available:
    - pyyaml
    - deepmerge
    - yaspin
    - kubernetes
    - debugpy

  It is recommended to set up a virtual environment for this project:
  
  ```
    export VALIDATION_PROJECT_PATH=<your preferred path>/validation-scenarios
    python3 -m venv $VALIDATION_PROJECT_PATH
    source $VALIDATION_PROJECT_PATH/bin/activate
    pip install pyyaml deepmerge yaspin kubernetes debugpy
  ```

  Whenever you want to run the validation scenarios again, simply re-activate your venv with:
  ```
    source $VALIDATION_PROJECT_PATH/bin/activate
  ```
  

You can run the following program to check if the modules are already installed:

**chkmodule.py**

```
import importlib.util

# List of required packages
packages = ['pyyaml', 'deepmerge', 'yaspin', 'kubernetes', 'debugpy']

for package_name in packages:
    if importlib.util.find_spec(package_name) is None:
        print(f"{package_name} is NOT installed.")
    else:
        print(f"{package_name} is already INSTALLED. You are good to go!")

```
[Back to Table of Contents](#table-of-contents)

## Preparing the environment

### Installing the Locust Kubernetes Operator
Before you start running the tests, we need to install the Locust Kubernetes Operator.   

**Step 1:** Clone the project using the appropriate Viya release and Git repository location:

```
git clone --branch <viya-release> <repository-location>/sas-validation-scenarios.git
```
For example, if you are running these scenarios against a 2025.08 viya you will use the following branch option:
```
git clone --branch <202x.x> <repository-location>/sas-validation-scenarios.git
```
Not specifying the branch/tag name during the clone operation will fetch the most recent version of the repo. 
If you have previously cloned this project from a previous release, you can switch to a newer release using the following commands:
```
git fetch origin
git checkout tags/<viya-release>
```
  
**Step 2:** Create a namespace called "testing".

  `kubectl create ns testing`
  
  NOTE: If you are using a shared k8s cluster where many different teams use the cluster to run load tests against various Viya environments such as for LoadGen (i.e. where the locust "virtual users" run), then it is recommended to uniquely name this namespace such as "team1tests", "team2tests" etc so as not to step on each other's environments.   
  

**Step 3:** Deploy the locust-k8s-operator in your testing namespace as follows:

  ```
  cd sas-validation-scenarios/framework/locust-k8s/
  
  export KUBECONFIG=$myAdminKubeConfigFile
  export TESTINGNAMESPACE=testing

  ./install-locust-k8s-operator.sh $TESTINGNAMESPACE $KUBECONFIG

  # You can run the following script to list all the resources that were just created
  ./list-locust-k8s-operator.sh $TESTINGNAMESPACE $KUBECONFIG

  # If you need to uninstall, run -> ./uninstall-locust-k8s-operator.sh $TESTINGNAMESPACE $KUBECONFIG
  ```

**Additional notes**

When you create the locust-operator these are the resources that gets created on your cluster: 

```
Globally scoped resources:
- customresourcedefinition.apiextensions.k8s.io/locusttests.locust.io                                     
- clusterrole.rbac.authorization.k8s.io/locust-operator-locust-k8s-operator  
- clusterrolebinding.rbac.authorization.k8s.io/locust-operator-locust-k8s-operator 

Namespace scoped resources:
- serviceaccount/default  
- serviceaccount/locust-operator-locust-k8s-operator
- role.rbac.authorization.k8s.io/locust-operator-locust-k8s-operator
- rolebinding.rbac.authorization.k8s.io/locust-operator-locust-k8s-operator
- deployment.apps/locust-operator-locust-k8s-operator 

```

**Step 4:**: We use a custom container image hosted in our **Azure Container Registry**. This image is configured with anonymous pull access, allowing teams across SAS to use it without additional authentication steps.

The framework is already configured to use this default image, so no additional setup is required.  

If you prefer to use your own custom-built image, feel free to contact me for assistance with the configuration process.

```
  image: sasvalidationscenarios.azurecr.io/loadtest-v1.2
```

[Back to Table of Contents](#table-of-contents)

## Configuring the Viya environment

Before running validation scenarios, make sure to disable the welcome screen and new user tour in Viya as follows:

   Edit the following property: 

   Environment Manager -> Configurations -> Definitions -> sas.htmlcommons 
   ```
    disableAutoOpenWhatsNew: true
    disableWelcomeScreens: true
   ```

## Optional: Creating a dedicated nodepool

This step is optional. By default these tests run on the system nodes with no taints and node affinity specifications. 

However tests can be executed in a dedicated **node pool** with separate nodes, which is highly recommended for performance or isolation reasons.
To do so, follw the steps below:

**Step 1:** Create a Nodepool on your k8s cluster with the following Labels and Taints

```
  Taints:
  managed-by=locust-k8s-operator:NoSchedule

  Labels:
  managed-by:locust-k8s-operator


```
**Step 2:** Add this section to your LocustTest (CRD) template file:

    You can find the LocustTest template here: sas-validation-scenarios/framework/python/templates/k8s-custom-resource.yaml.template
```
  labels: 
    master:
      locust.io/role: "master"
    worker:
      locust.io/role: "worker"
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        managed-by: locust-k8s-operator
  tolerations: 
    - key: "managed-by"
      operator: "Equal"
      value: "locust-k8s-operator"
      effect: "NoSchedule"


```
[Back to Table of Contents](#table-of-contents)

## Defining test users

Testing users can be provided within a users.csv file. The list of users and their passwords should be in the format below:
Make sure these are test users and not actual users with actual passwords as this file is not encrypted for security. 

```
user1,password1
user2,password2
user3,password3
``` 

If you have 100 users that you want to do testing with, you could provide all the 100 users with their passwords in this file. 
Locust does a random sampling of the users and will pass the list to its workers. In other words you can have more users 
in your users.csv than the number of users you will be testing with. 
However, you cannot have less users in the users.csv than you will be testing with. 

Eg: If you are testing with 100 users, you have to have at least 100 or more number of users in 
the users.csv

There is a template file available in the sas-validation-scenarios/validation-scenarios folder called users.csv.template
Modify this file accordingly to match your system. 

A few things to be mindful about:
Make sure the users are non admin users, the users exist in your system and that you are manually able to log in and perform these tasks as this user. 


[Back to Table of Contents](#table-of-contents)

## Providing User Credentials

You can provide user credentials to your workloads in two ways:

### 1. Pass them as file using a parameter
Prepare a users.csv file with your user names and passwords.
Set the environment variable usersFileFullPath to the full path of your users.csv file before running the script.
The script will include this file in the generated ConfigMap.

Example:

```
./generateWorkloads.sh -g ./global-config.yaml -w ./workload-definitions/helloviya-advanced-wrkld-def.yaml -u users.csv
```

### 2. Store them in Kubernetes Secrets

If you do not provide the users file as a parameter, the execution scripts will automatically look for credentials stored in Kubernetes Secrets.  
To load the users and passwords into Kubernetes Secrets, use the provided script. Once the credentials are successfully loaded, you can safely delete the local files — they are no longer required by the Validation Scenarios framework.  
All subsequent test runs will retrieve credentials directly from Kubernetes Secrets.

Initializing User Names with initUserNames.sh

Usage:
```
./initUserNames.sh -u <users-file> -n <namespace>
```
Parameters:

- -u <users-file>: Path to the CSV file containing user names and passwords (e.g., ./configs/users-25.csv).
- -n <namespace>: Kubernetes namespace where the Validation Scenarios have been setup (e.g., testing).

Example:
```
./initUserNames.sh -u ./configs/users-25.csv -n testing
```

[Back to Table of Contents](#table-of-contents)

## Running Scenarios

```
Before you start, make sure:
- Welcome screen and new user tour is disabled. 
- SAS Studio is installed, compute nodes are available
- Manual login to sas studio is successful and a compute server is created correctly
- Users secified in users.csv file exists on your Viya system
- Make sure the users specified in the users.csv file are NON ADMIN users

```

1. `cd sas-validation-scenarios/validation-scenarios`  

2. `cp global-config-simple.yaml.template global-config.yaml`
3. Edit the  global-config.yaml with values to match your environment.

  Modify the following values in this file:

```
hostname: https://my-viya-system.sas.com
# Kube config: [some location]/.kube/config
kube-config: [some location]/.kube/config
```

4. `cp users.csv.template users.csv`

5. Modify the users to match the users in your environment. 

6. In the workload-definitions folder, you will find a matching workload-definition yaml for each scenario defined in the  sas-validation-scenarios/validation-scenarios/scenarios folder.
The names of these definitions files are self explanatory.  

7. By default the workload-definitions are set to run with a single user. In order to run with variable number of users and do a result capture and analysis, see section below on "Results Analysis". 

## Single scenario example: helloviya-simple

The helloviya-simple test is a short logon/logoff test. This test goes to the /SASLogon URL, signs in, and then signs out. 
For this exercise, we will be using `helloviya-simple-wrkld-def.yaml`.

To run the `helloviya-simple` test:

```
# creating the generated workload folders (-u users.csv is not required if usernames/passwords have been stored in K8s Secrets)
./generateWorkloads.sh -g ./global-config.yaml -w ./workload-definitions/helloviya-simple-wrkld-def.yaml -u users.csv

# creating the artifacts and scripts for the scenario execution 
./generated/workload-execution/runAllCreateWorkloadArtifacts.sh

# to execute the helloviya-simple scenario 
cd ./generated/workload-execution/helloviya-simple/artifacts
./runWorkload.sh

# logs from master and worker pods can be found in the following location:
./execution-logs

# results of this run can be found in the following location:
./results

```

At this point, the tests have been executed with a single user, and the results are stored in the `results` folder within the artifacts directory.  
You can now rerun the same scenario with varying numbers of users to observe performance changes and perform a scaling analysis using the saved results.  
For detailed instructions on running variable user loads, capturing results, and analyzing performance, refer to the section below titled **"Results Analysis"**.

[Back to Table of Contents](#table-of-contents)

## Single scenario example: helloviya-advanced

The helloviya-advanced test is a more in-depth set of Viya end to end tests that goes thru various SAS Viya applications and make sure applications are alive and well. 

For this exercise, we will be using `helloviya-advanced-wrkld-def.yaml`.

To run the helloviya-advanced test:

```
# creating the generated workload folders (-u users.csv is not required if usernames/passwords have been stored in K8s Secrets)
./generateWorkloads.sh -g ./global-config.yaml -w ./workload-definitions/helloviya-advanced-wrkld-def.yaml -u users.csv

# creating the artifacts and scripts for the scenario execution 
./generated/workload-execution/runAllCreateWorkloadArtifacts.sh

# to execute the helloviya-advanced scenario 
cd ./generated/workload-execution/helloviya-advanced/artifacts
./runWorkload.sh

# logs from master and worker pods can be found in the following location:
./execution-logs

# results of this run can be found in the following location:
./results

```
At this point, the tests have been executed with a single user, and the results are stored in the `results` folder within the artifacts directory.  
You can now rerun the same scenario with varying numbers of users to observe performance changes and perform a scaling analysis using the saved results.  
For detailed instructions on running variable user loads, capturing results, and analyzing performance, refer to the section below titled **"Results Analysis"**.

## Mixed scenario example: mixed-studio-vf

This example demonstrates how to run a workload containing multiple mixed scenarios packaged together.  
In this case, users first execute the **sas-studio** scenario, followed by the **vf-forecasting** scenario, both with a defined number of users.  The scenarios run sequentially; all users complete the **sas-studio** scenario simultaneously before proceeding to run the **vf-forecasting** scenario.

For this exercise, we will be using `mixed-studio-vf-wrkld-def.yaml`.

To run the `mixed-studio-vf` workload:

```
# creating the generated workload folders (-u users.csv is not required if usernames/passwords have been stored in K8s Secrets)
./generateWorkloads.sh -g ./global-config.yaml -w ./workload-definitions/mixed-studio-vf-wrkld-def.yaml -u users.csv

# creating the artifacts and scripts for the scenario execution 
./generated/workload-execution/runAllCreateWorkloadArtifacts.sh

# to execute the mixed workload scenario 
cd ./generated/workload-execution/studio-vf-workload/artifacts
./runWorkload.sh

# logs from master and worker pods can be found in the following location:
./execution-logs

# results of this run can be found in the following location:
./results

```
At this point, the tests have been executed with a single user, and the results are stored in the `results` folder within the artifacts directory.  
You can now rerun the same scenario with varying numbers of users to observe performance changes and perform a scaling analysis using the saved results.  
For detailed instructions on running variable user loads, capturing results, and analyzing performance, refer to the section below titled **"Results Analysis"**.

[Back to Table of Contents](#table-of-contents)

# Execution Logs
When you run the runWorkloads.sh script, an execution-logs folder is created in the artifacts directory. This folder holds the logs from all the master 
and worker pods of the tests run. A merged file that contains the merged results from the logs. This folder also holds the exception and failure logs (in the form of csv) of the runs.

A few tips and tricks to scan the logs for important information. 

```
execution-logs % ls -al *.csv
-rw-r--r--  1  31 Jun 23 12:10 1-studio-01-exceptions.csv
-rw-r--r--  1  31 Jun 23 12:10 1-studio-01-failures.csv
-rw-r--r--  1  31 Jun 23 12:12 1-studio-02-exceptions.csv
-rw-r--r--  1  31 Jun 23 12:12 1-studio-02-failures.csv
```

Notice how the size of exceptions.csv and the failures.csv is 31 bytes. These are the default size of these files and this generally indicates that there were no exceptions or failures. If you see a different size, that usually indicates there was an error or an exception. 

```
cat studio-01_merged.log | grep error
cat studio-01_merged.log | grep Failed
```
Each of the scripts have built in logging to indicate what the tests are doing at each stage of their execution.
And we have made an effort to standardize these log messages so scanning teh logs for errors and failures can be easy and fast. 
Usually you will see messages as below in the locust-worker logs. 

```
[2025-06-23 16:09:08,764] studio-01-test-worker-ghtms/INFO/studio-01: Authenticating to SASLogon
[2025-06-23 16:09:09,135] studio-01-test-worker-ghtms/INFO/root: Logging in as user: hruser8
[2025-06-23 16:09:09,502] studio-01-test-worker-ghtms/INFO/studio-01: Authentication Successful
[2025-06-23 16:09:09,602] studio-01-test-worker-ghtms/INFO/studio-01: Navigating to SAS Studio
[2025-06-23 16:09:14,735] studio-01-test-worker-ghtms/INFO/studio-01: Start: Creating Studio Compute Context
[2025-06-23 16:09:29,048] studio-01-test-worker-ghtms/INFO/studio-01: Finished Creating Studio Compute Context
[2025-06-23 16:09:29,149] studio-01-test-worker-ghtms/INFO/studio-01: Start: Run SAS Program
[2025-06-23 16:10:06,520] studio-01-test-worker-ghtms/INFO/studio-01: Finished Running SAS Program
[2025-06-23 16:10:06,520] studio-01-test-worker-ghtms/INFO/studio-01: TESTS FINISHED
```
[Back to Table of Contents](#table-of-contents)

## What to Expect When You Execute runWorkloads

When you run deployTaskResourcesAsConfigMap.sh a config map is created in the testing namespace, which looks like this. All scripts that we need to exeute as part of the workload gets packaged as a config map. 

![config-map](framework/images/config-map.png){width=60%}


When you run the runWorkload.sh script, the locust master- worker pods will start up (this example assumes 5 users are running the tests)

![runWorkload](framework/images/runWorkload.png){width=60%}

Here all locust master/worker pods have been scheduled, the images are pulled and the pods are running. 

![locust-master-worker](framework/images/locust-master-worker.png){width=60%}

The presence of running Locust master and worker pods does not necessarily mean that the tests have started. After the pods are initialized, the Locust master attempts to connect to all worker pods. Test execution on the workers does not begin until every worker has successfully connected to the master.  
This synchronization ensures that all tests across all workers start simultaneously, providing consistent and accurate load generation.

> I have noticed that sometimes the locust master and worker pods takes an extended time to connect. The maximum observed is approxiamtely 160 secs (2 min 40 sec). This is a project TO-DO list item to research and improve.

![master-status](framework/images/master-status.png){width=60%}

![master-worker-connected](framework/images/master-worker-connected.png){width=60%}

The worker logs display the progress of each test, indicating the current execution step.  
A new script is being developed to collect logs from all workers in real time and aggregate them into a single consolidated log file. This feature will be available soon.

![worker-log](framework/images/worker-log.png){width=60%}

Below is a screenshot of a successful test. When all tests complete, the worker status changes to `Succeeded`.

![worker-finished](framework/images/worker-finished.png){width=60%}

[Back to Table of Contents](#table-of-contents)
