This scenario runs the sas-viya cli commands in a locust master-worker setup. 

No install of sas-viya cli is necessary as the docker image that we will be using for these tests includes the sas-viya cli in it. 

This image has the sas-viya excutable and all the plugins built into the image. 
The image resides in our azure container repository and is set up to have anonymous pull access which allows for users to have full access to the image.

`image: sasvalidationscenarios.azurecr.io/loadtest-v1.2`

In order to run this scenario, you will need the following from your viya environment:

- A valid **trustedcerts.pem** file from your viya environment. Place this file in the sas-validation-scenarios/framework/execution/common folder and make sure the file is named "trustedcerts.pem"
  
  This can be obtained as follows:
  
  `kubectl -n viya cp $(kubectl get pod -n viya | grep "sas-logon-app" | head -1 | awk -F" " '{print $1}'):/security/trustedcerts.pem /tmp/trustedcerts.pem`
 
- A valid **config.json** file with a definition for the default profile. 

  Place this file also in the sas-validation-scenarios/framework/execution/common folder and make sure the file is named "config.json"

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
The tests folder under the sas-viya-cli folder consists of a set of python files that runs the sas-viya cli batch programs at load using locust. 

Each python file is the main python file that runs the sas program with the same name in the sas-viya-cli/resources folder. 
The sas programs in the resources folder are used as input for the python programs in the tests folder. 

The workload-definition associated with this scenarios is as follows:

`sas-viya-cli-wrkld-def.yaml`

# How to Execute sas-viya-cli scenarios

Before you begin .... 

```
- Make sure you have copied the trustedcerts.pem file from your viya environment into the  sas-validation-scenarios/framework/execution/common/ folder 
- Also make sure the file is named "trustedcerts.pem" 
- Make sure you have copied the config.json file with a definition for the default profile into the sas-validation-scenarios/framework/execution/common/ folder
- Also make sure the file is named "config.json" 
- Make sure you have the path to the trustedcerts.pem file correctly defined in the global-config.yaml file

```

**Generating Workload and running the sas-viya-cli scenario:**

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

To learn more about sas-viya cli refer to this page;
https://go.documentation.sas.com/doc/en/sasadmincdc/v_077/calcli/titlepage.htm

Open an interactive session to sas-viya cli and log in as an SAS admnistrator. Here are some useful commands:

    sas-viya batch jobs list (lists all jobs running)
    sas-viya batch jobs get-results --id <id>

# sas-viya cli scenarios list

| testcase        | Details                              | sas program | resources/inputdata | 
|------------------|---------------------------------------------|----------|---------| 
| **test.py** | **test.sas** | Runs test.sas program in batch which does a sleep for 120 sec | None |     

  