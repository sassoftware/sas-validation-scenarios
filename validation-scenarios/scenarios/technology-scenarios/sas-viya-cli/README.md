| testcase        | Details                              | sas program | resources | 
|------------------|---------------------------------------------|----------|---------| 
| **test.py** | Runs batch sas program which does a sleep for 120 sec | test.sas | None |     



This scenario runs the sas-viya cli commands in a locust master-worker setup. 
No install of sas-viya cli is necessary as the docker image that we will be using for these tests includes the sas-viya cli in it. 
This image has the sas-viya excutable and all the plugins built into the image. 
The image resides in our azure container repository (see below). 
This image is set up to have anonymous pull access which allows for teams across SAS full access to the image.

`image: sasvalidationscenarios.azurecr.io/loadtest-v1.2`

In order to run this scenario, you will need the following from your viya environment:

- A valid **trustedcerts.pem** file from your viya environment. Place this file in the sas-validation-scenarios/framework/execution/common folder. 
  Also make sure the file is named "trustedcerts.pem"
  This can be obtained as follows:
  `kubectl -n viya cp $(kubectl get pod -n viya | grep "sas-logon-app" | head -1 | awk -F" " '{print $1}'):/security/trustedcerts.pem /tmp/trustedcerts.pem`
 
- A valid **config.json** file with a definition for the default profile. Place this file also in the sas-validation-scenarios/framework/execution/common folder. 
  Also make sure the file is named "config.json"

An example config.json file should look like this:

```
{
  "Default": {
    "ansi-colors-enabled": "false",
    "oauth-client-id": "sas.cli",
    "output": "text",
    "sas-endpoint": "https://myviya.domain.com"
  }
}
```

# sas-viya cli execution files
This folder consists of a set of python files that runs the sas-viya cli batch programs at load using locust. 
Each python file is the main python file that runs the sas program with the same name in the resources folder. 
A description of what each program does is detailed below. 
The sas programs in the resources folder are used as input for the python programs in this folder. 
The data needed to run these tests can be found in the other [resources](https://gitlab.sas.com/aat/sas-validation-scenarios-resources.git) repo. 

The workload-definition associated with this scenarios is as follows:

`sas-viya-cli-wrkld-def.yaml`


# How to Execute sas-viya-cli scenarios

THE FOLLOWING STEPS WILL BE REPLACED WITH A BETTER SOLUTION MOVING FORWARD! 
For now, we will need to copy these following files as described below:

```
Make sure you have copied the  trustedcerts.pem file from your viya environment into the  sas-validation-scenarios/framework/execution/common/ folder. Also make sure the file is named "trustedcerts.pem" 
Make sure you have copied the config.json file with a definition for the default profile into the sas-validation-scenarios/framework/execution/common/ folder. Also make sure the file is named "config.json" 
Copy the sas programs in the resources folder to the sas-validation-scenarios/framework/execution/common/ folder.
     cd sas-validation-scenarios
     cp sas-validation-scenarios/validation-scenarios/scenarios/sas-viya-cli/resources/*.sas sas-validation-scenarios/framework/execution/common
Make sure you have the path to the trustedcerts.pem file correctly defined in teh global-config.yaml file.
```

Generating Workload and running the sas-viya-cli scenario

```
cd sas-validation-scenarios/validation-scenarios

# creating the generated workload folders
./generateWorkloads.sh -g ./global-config-simple.yaml -w ./workload-definitions/sas-viya-cli-wrkld-def.yaml -u users.csv

# creating the artifacts and scripts for the scenario execution 
./generated/workload-execution/runAllCreateWorkloadArtifacts.sh

# to execute the sas-viya-cli scenario 
./generated/workload-execution/sas-viya-cli/artifacts/runWorkload.sh

# logs from master and worker pods can be found in the following location:
./generated/workload-execution/sas-viya-cli/artifacts/execution-logs

# results of this run can be found in the following location:
./generated/workload-execution/sas-viya-cli/artifacts/results
```


# Monitoring sas-viya cli jobs and getting results of test execution
You will need to have an install of sas-viya cli to monitor the jobs running via the sas-validation-framework. 

If you are new to sas-viya command line interface, refer to this doc to get started:

https://go.documentation.sas.com/doc/en/sasadmincdc/v_064/calcli/titlepage.htm

Open an interactive session to sas-viya cli and log in as an SAS admnistrator. Here are some useful commands:

    sas-viya batch jobs list (lists all jobs running)
    sas-viya batch jobs get-results --id <id>

  