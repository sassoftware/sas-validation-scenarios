# What's New in each release?

## 2026.04 (BREAKING CHANGES)
<details>
  <summary> Upgrade to Locust kubernetes operator 2.2.3</summary>

This is a BREAKING CHANGE update and will require you to re-install the new version of the locust operator using the new instructions provided.

This version of locust operator has the ability to mount shared PVC storage to the locust pods/containers so that locust can directly write output files (logs, sas-viya-cli output etc) directly to this mount. The /data is available as a mount point on all locust master and worker pods. 

With this change the custom resource spec template has changed as well. 
And in addition a locust_pvc.yaml file has been added to create the pvc to mount this location. 

</details>

<details>
  <summary> Insurance Capital Management (ICM) scenario added </summary>
A new solution scenario that targets sas-viya batch cli has been added in this release. For more details refer to the ICM_Readme.md doc.
[](./validation-scenarios/scenarios/solution-scenarios/sas-insurance-cap-mgt/ICM_Readme.md))
</details>

