The helloviya-advanced test is a more indepth set of viya end to end tests that goes thru various 
SAS viya aplications and makes sure applications are alive and well.

| testcase        | Details                              | resources   | SAS Content | 
|------------------|---------------------------------------------|----------|------- | 
| **st_runsleep01.py** | Runs sas sleep program for 30 sec | sleep_20.sas  | None |      
| **st_runsleep02.py** | Runs sas sleep program for 60 sec | sleep_40.sas | None | 
| **va_simplecreate01** | Creates a simple VA report using class data set |  class.csv  | None | 