## Results Analysis in SAS Visual Analytics
> [!IMPORTANT]  
> This section is a work in progress.
> Additional improvements will be available soon.

By default, each scenario runs for a single user.
As part of scaling analysis, we will want to run these scenarios first with a single user then increase the number of users to 2, 3, 5, 7, 9,12 ..... and so on to see what kind of scaling patterns we see as we ramp up the number of users. 
This can be achieved as follows:

We will use the helloviya-advanced scenario as an example to walk through this process. 

```
# creating the generated workload folders
./generateWorkloads.sh -g ./global-config.yaml -w ./workload-definitions/helloviya-advanced-wrkld-def.yaml

# creating the artifacts and scripts for the scenario execution 
./generated/workload-execution/runAllCreateWorkloadArtifacts.sh

# cd to the artifacts directory
cd generated/workload-execution/helloviya-advanced/artifacts/

# to execute the helloviya-advanced scenario 
./runWorkload.sh

# logs from master and worker pods can be found in the following location:
# A new execution-logs gets created for each ruWorkload.sh run
# The older execution-logs gets renamed and saved in that same folder. 
ls -al execution-logs

# results of this run can be found in the following location:
# THE results FOLDER DOES NOT GETS OVER WRITTEN EACH TIME YOU RUN runWorkload.sh
ls -al results
```

By default, the scenarios run with a single user. The results from this run is saved in the results folder as a csv file with a prefix which is the number of users the scenario ran with such as 1_logonoff.csv

Unlike the execution-logs folder the results folder in the artifacts dir  does not gets overwritten after each runWorkload.sh 
The logonoff.csv gets saved in the results folder such as this 1_logonoff.csv, 5_logonoff.csv 10_logonff.csv etc 
Later we can collect the results from the  different runWorkloads run for analysis in SAS Visual Analytics to see scaling patterns and odd behaviors. 

> [!NOTE]  
> The exceptions and failures files from the locust master pods are  named as the <testname>_exception.csv and <testname>_failures.csv and placed in the execution-logs folder.

Now, to run with a different number of users follow the steps below:

> [!NOTE]  
> This process will be automated soon where we will have a script to generate the crd yaml using a overrides file. 
> For now this has to be done manually using the following sed command. 

```
# initial numebr of users
win=1
# new number of users
wout=3

sed -i "" "s/users ${win}/users ${wout}/g" k8s-cr-studio-01.yaml 
sed -i "" "s/workerReplicas: ${win}/workerReplicas: ${wout}/g" k8s-cr-studio-01.yaml 
sed -i "" "s/workerReplicas: ${win}/workerReplicas: ${wout}/g" k8s-cr-studio-02.yaml 
sed -i "" "s/users ${win}/users ${wout}/g" k8s-cr-studio-02.yaml 

# run the runWorkload.sh script again. 
./runWorkload.sh 

```

Once you have finished all the runs by varying the number of users, the results folder should look something like this: 



Now we do some results analysis with these csv files.
