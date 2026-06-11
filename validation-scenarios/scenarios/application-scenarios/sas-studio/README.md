Before you run this scenario, please makes sure to go to the resources section and create the SAS Content necessary to run  this scenario. 

| testcase        | Details                              | resources | SAS Content | 
|------------------|---------------------------------------------|----------|------| 
| **st_runsleep01.py** | Runs sas sleep program for 20 sec | sleep_20.sas  |   None |   
| **st_runsleep02.py** | Runs sas sleep program for 40 sec | sleep_40.sas | None | 
| **st_analystoptimizeflow.py** | Runs Data Flow flow_from_analyst_optimize.flw Runs for about 2-3 min  |  None (uses sashelp data) | flow_from_analyst_optimize.flw |
|**st_queryflow.py**  | Runs Data Flow queryFlow.flw Runs for about 3-4 min  | None (uses sashelp data). | queryFlow.flw  |
|**st_40nodesflow.py** | Runs Data Flow 40nodes.flw Runs for about 3-4 min. | None (uses sashelp data) | 40nodes.flw.  |
