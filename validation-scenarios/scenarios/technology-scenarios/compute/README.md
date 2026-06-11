This scenario runs complex compute intensive workloads. 
These can be run using sas studio, viya cli or rest api. 

These compute scenarios under the technology-scenarios are grouped as compute intensive tests that will 
require adjustment to spre container mem and cpu limits . 

This flow requires the memsize be set to a higher number: generally between 14G to 16G 
MAke suer you ahev enough comute resources before you run these scenarios. 
cpu limits; 4 mem: 8G

Open environment manager, contexts, compute context, select your context (SAS Studio Compute context)
 
advanced tab: Add this opetion bekow:
-memsize  14G
 