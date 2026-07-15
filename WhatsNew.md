# What's New in each releases?

## 2026.04

Upgrade to Locust operator form 2.2.2 to 2.2.3
This is a HUGE update with lots of changes. See below fo reverything thta has changed. 

This version of locust operator has the ability to mount shared PVC storage to the locust pods/containers so that locust can directly write output files (logs, sas-viya-cli output etc0 directly to this mount. The /data is available as a mount point on all locust master and worker pods. 

With this change the custom resource sepc template has changed as well. 
And in addition a locust_pvc, yaml file has been added to create the pvc to mount this location. 
Very Imp: Also, the instruction sto install the locust operator has changed as well. 

