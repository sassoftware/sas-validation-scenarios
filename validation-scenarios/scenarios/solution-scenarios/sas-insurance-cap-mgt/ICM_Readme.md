SAS Insurance Capital Management Environment Setup and Validation Guide
________________________________________

**1. Prerequisite**
-	Install the required Python packages for the SAS Insurance Capital Management (ICM) deployment by downloading the package from the specified location. 
**../../../resources/solutions/ICM**

**2. Environment Deployment**
-	Deploy a SAS Viya environment using standard deployment automation process.
-	Ensure the following solution components are included during deployment.

       **SAS Insurance Capital Management on Viya4**

**ICM Rick cirrus mandatory pods:**

Confirm that the following ICM core services are deployed and healthy:

-	sas-risk-cirrus-core
-	sas-risk-data
-	sas-risk-scenarios
-	sas-risk-cirrus-objects
-	sas-risk-rrf-core
-	rrf
-	sas-fermi
-	sas-fermi-worker
-	sas-fermi-redis-server
 

**3. Input Data**
- The small-volume dataset is included as part of the standard deployment and is automatically loaded during environment setup.


| Schema         | Table Size | Index Size | Total Size |
|----------------|------------|------------|------------|
| icm_staging_s2 | 630 MB     | 1197 MB    | 1838 MB    |


________________________________________
**4. Input Parameter Excel Files**
- The input parameter Excel files are delivered as part of the standard deployment and are available at the following location:

**/Products/SAS Insurance Capital Management/&cadence./spre/sas/batch**
________________________________________
**5. Execution**

 Two scripts are provided as part of the execution process:

1.	A SAS program script that contains the workflow and business process execution logic - **icm_batch.sas**
2.	A Python script that automates the execution of the SAS program - **icm_batch.py**

**The workflow executes the following business transactions:**
1.	Run Data Quality
2.	Review Data Quality Results
3.	Solvency II Analysis
4.	Review Results
5.	Create QRT Reports
6.	Sign-Off
________________________________________
**6. Monitoring Test Execution**

After the batch job is submitted:
-	Monitor execution through the corresponding Analysis Run within the ICM application.
-	Review logs for failures or performance issues.
________________________________________
**7. Reports – For capturing Response Time**
- Upon successful completion, benchmark results are generated in Excel format.
- The output report is available under the Audit Report section for the corresponding Analysis Run.

