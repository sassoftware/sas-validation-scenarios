# Scenarios
The `scenarios` folder contains the individual use cases used for validation.
Each scenario bundles the required resources and test scripts necessary for execution.
Before running the tests, several prerequisites may need to be completed—such as loading data, creating CAS libraries, importing projects, or generating reports.
Refer to the [Resource-Setup](./RESOURCES-SETUP.md) section to finish the pre-requisites before running the tests.

Each scenario represents a specific use case and includes everything needed to configure and validate your SAS Viya environment.
Ensure that your Viya environment is properly set up with all required content before executing any scenario.

If the required setup is incomplete, the tests may fail.  
For example, running a **Visual Analytics** test case without the associated reports, data sources, formats, or dependent objects will result in errors during execution.

### helloviya-simple

| testcase        | Description                              | data  | SAS Content |  Approx runtime  
|------------------|---------------------------------------------|----------|------- | -------|
| **logonoff.py** | Logs on/off from SASLogon | None |  None  |      | 
| **createcompute.py** | Creates a compute session in SAS Studio | None | None |   | 

### helloviya-advanced 

The helloviya-advanced test is a more indepth set of viya end to end tests that goes thru various 
SAS viya aplications and makes sure applications are alive and well.

| testcase        | Details                              | data   | SAS Content |  Approx runtime |
|------------------|---------------------------------------------|----------|------- | ------|
| **st_runsleep01.py** | Runs sas sleep program for 30 sec | None  | sleep_20.sas |      |
| **st_runsleep02.py** | Runs sas sleep program for 60 sec | None | sleep_40.sas |   |
| **va_simplecreate01** | Creates a simple VA report using class data set |  class.csv  | None |    | 

### SAS Studio  

Before you run this scenario, please makes sure to go to the resources section and create the SAS Content necessary to run  this scenario. 

| testcase        | Details                              | data | SAS Content |  Approx runtime | 
|------------------|---------------------------------------------|----------|------| ----- | 
| **st_runsleep01.py** | Runs sas sleep program for 20 sec | None  |   sleep_20.sas |   |
| **st_runsleep02.py** | Runs sas sleep program for 40 sec | None | sleep_40.sas |    |
| **st_analystoptimizeflow.py** | Runs Data Flow flow_from_analyst_optimize.flw Runs for about 2-3 min  |  None (uses sashelp data) | flow_from_analyst_optimize.flw |  | 
|**st_queryflow.py**  | Runs Data Flow queryFlow.flw Runs for about 3-4 min  | None (uses sashelp data). | queryFlow.flw  |    |
|**st_40nodesflow.py** | Runs Data Flow 40nodes.flw Runs for about 3-4 min. | None (uses sashelp data) | 40nodes.flw.  |.   | 

### Visual Analytics 

| testcase        | Details                              | data  | SAS Content  |   Approx runtime | 
|------------------|---------------------------------------------|----------|-------|----- | 
| **va_simplecreate01** | Creates a simple VA report using class data set |  class.csv | None |    | 
| **vdmml_simplecreate01.py** | validates vdmml features using Gradient Boosting, Forest, Neural Network | gendata01M_01_visual_0101_vars.sashdat |  None  |  | 
| **vs_simplecreate01.py** | validates Visual Statistics features using regselect, logselect, glmselect and dtree | reg_simtbl_vsbench_200M.sashdat  |  None |    |   

## Resource-Setup

The scenarios expect contents such as data, sas studio flows, va reports, sas programs and other items in order to run successfully. 
These resources are all available in the sas-validation-scenarios/validation-scenarios/resources folder.
They need to be uploaded to the viya system before the tests can be run successfully. 

Currently the process to load SAS Content is a manual process by the user loading them into their system themselves.
This step however is going to be automated soon. 

| Content Type       | Details                              | Location  |  
|------------------|---------------------------------------------|----------|
| data| datasets that needs to be loaded to cas  |  CAS Public Library | 
| dataflows|SAS Studio Flows (Use SAS Studio to upload)  | SAS Content --> Public |  
| sas_program | sas programs (Use SAS Studio to upload)  | SAS Content--> Public  |
