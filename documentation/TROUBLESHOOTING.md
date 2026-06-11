# Troubleshooting
This page is designed to help users identify, diagnose, and resolve problems relating to the usage of SAS Validation Scenarios. 

## Problem: Unable to access viya url

### Overview
When running validation scenarios, we have noticed situations where the locust master and worker pods are unable to access the viya url. 
We have noticed these in eks clusters and also when unning the validation scenarios in one cluster and Viya in another.
When you run the tests, you would get error messages about not being able to connect to the supplied URL, and eventually would get a load timeout error in the stats_failures file on the master pod.

```
event,01: Navigate to SASLogon,"CatchResponseError('Page.goto: Timeout 60000ms exceeded.Call log:  - navigating to ""https://myviya.domain.org/SASLogon"", waiting until ""load""')",5

OR

TASK,logonoff.test_logonoff,CatchResponseError('Page.screenshot: Timeout 60000ms exceeded.Call log:  - taking page screenshot  -   - waiting for fonts to load...  -   - fonts loadedabout:blank'),1
```

When the locust pods (master and workers) are running Kubernetes, they try to access the web site via the external hostname 
(ex. https://yourviya.domain.org).
As is normally the case in this situation in kubernetes, the public ip address of the pods 
need to be added to the NGINX Ingress service definition.
All pods that access the outside world get the same public ip address, the one that is associated with the NAT Gateway for that subnet.
You always need the public ip addresses in the loadBalancerSourceRanges list.

### How to debug

Exec into the locust master pod. There was no curl, wget, etc. in that container.  However, there was python and python3.

Run this code in python (in the master pod container) to retrieve the public ip address:

```
   import requests   
   response = requests.get('https://ifconfig.me')
   print(f"Content: {response.content}")
```

You will see what the public ip address is of the pod in the printf of the response content.
This ip address needs to be added to the loadBalancerSourceRanges of the NGINX service definition.

In AWS, you will also need the NAT gateway definitions for the VPC and get their Public IP addresses associated with them
You will alos need to add this ipaddress to the loadBalancerSourceRanges of the NGINX service definition.

### Solution

`kubectl edit service ingress-nginx-controller -n ingress-nginx`

Add both the public ip address to the loadBalancerSourceRanges as x.x.x.x/32

## Problem: AWS Authentication Saturation with EKS kubeconfig During Locust Scaling

### Overview

Issue encountered when deploying large numbers of Kubernetes workers (for example, 200 Locust workers) using a standard AWS-generated kubeconfig.
The standard kubeconfig generated using 'aws eks update-kubeconfig' contains an exec authentication block that runs 'aws eks get-token' whenever authentication is required. When many Locust workers start simultaneously, each worker independently triggers AWS token generation. This results in a surge of AWS STS authentication calls.
Observed impacts include:
· AWS API throttling and authentication saturation
· Slower Kubernetes worker deployment times
· Increased infrastructure overhead unrelated to workload testing
· Reduced reliability during large-scale deployments

### Root Cause
The default kubeconfig dynamically retrieves authentication tokens using AWS CLI exec calls. This works well for interactive use but does not scale efficiently when hundreds of parallel workers request authentication simultaneously.

### Proposed Solution

Generate a static kubeconfig file that contains a pre-generated temporary Kubernetes token. This removes the runtime dependency on AWS authentication for each worker and significantly reduces the number of AWS API calls during deployment.
Benefits of the Static Token Approach
· Eliminates large bursts of AWS authentication calls
· Improves deployment speed and reliability
· Reduces risk of AWS throttling
· Provides more stable high-scale Locust deployments

### Considerations
The static token is temporary and must be regenerated periodically.
For long-running tests, generate a new static kubeconfig before the token expires.
