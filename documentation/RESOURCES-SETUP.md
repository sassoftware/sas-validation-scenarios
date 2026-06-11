# Resources Setup

The scenarios expects content such as data, sas studio flows, va reports, sas programs and other items in order to run successfully. 
These resources are all available in the sas-validation-scenarios/validation-scenarios/resources folder. They need to be uploaded to the viya system before the tests can be run successfully. 

Currently the process to load SAS Content is a manual process by the user loading them into their system themselves. This step however is going to be automated soon. 

| Content Type       | Details                              | Location  |  
|------------------|---------------------------------------------|----------|
| data| datasets that needs to be loaded to cas  |  CAS Public Library | 
| dataflows|SAS Studio Flows (Use SAS Studio to upload)  | SAS Content --> Public |  
| sas_program | sas programs (Use SAS Studio to upload)  | SAS Content--> Public  |
