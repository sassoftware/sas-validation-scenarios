# Running Validation Scenarios Outside of Kubernetes Using Locust Commands

Clone this project using the appropriate Viya release and Git repository location:

```
git clone --branch <viya-release> <repository-location>/sas-validation-scenarios.git
```
Navigate to the following directory: 
```
cd sas-validation-scenarios/validation-scenarios/locust-commandline
```
Your current working directory should be locust-commandline

This folder has a folder called scenarios. You can run any of the scenarios using the locust command line. 

```
Before you start, make sure: 

- You have a vm you can run tests on, this could also be your laptop. 
- Ensure that your vm has sufficient resources for multi-user tests. 

   For example, if your VM has 8 CPUs, running 10 concurrent users may overload the system.
   In this case limiting the load to 2–3 users typically yields better results.
 
- This vm has access to your viya URL
- Welcome screen and new user tour is disabled. 
- SAS Studio is installed, compute nodes are available
- Manual login to sas studio is successful and a compute server is created correctly
- Users secified in users.csv file exists on your Viya system
- Make sure the users specified in the users.csv file are NON ADMIN users
- **Very Imp:** Make sure you have loaded all the content required to run these tests
  Refer to the Resource-Setup section to make sure all the content needed to run the scenarios is available in 
  your viya environment. 

```
## Additional Setup

1. Make sure python and pip3 is installed 
2. Make sure your python venv is correctly set
3. Install the following using pip:

-   pip3 install locust
-   pip3 install playwright locust locust-plugins 
-   playwright install 
-   playwright install-deps 
-   pip3 install kubernetes ( I think this is not needed)

4. Create a users.csv file such as this and place it in the test folder 

```
user1,pass1
user2,pass2
user3,pass3
user4,pass4
user5,pass5
```

## Running headed vs headless: 

You can run these tests on a local VM with one or a few users, in either **headed** or **headless** mode.  
- In **headed mode**, a live browser window opens, allowing you to observe the test execution in real time.  
  Do not use this option for more than 2-3 users, else you will have that many browsers open up 
  on your VM as the number of users you are specifying. 

- In **headless mode**, tests run silently in the background without displaying the browser.

By default the scenarios run in headed mode, meaning you will see a live browser come up and execute the tests. 
But if you want to run them in a headless mode, modify the following PlaywrightUser setting in the events.py 
The events.py file resides in this same folder. 

```
**HEADLESS MODE**
PlaywrightUser.headless = True 

**HEADED MODE**
PlaywrightUser.headless = False
```

### Run scenarios using locust command line 

There are many testcases inside the scenarios folder. You could run any one of the usecase using the command below. 
There are also soem ready made scripts such as runALL_StudiTests.sh which will run all SAS Studio tests in the scenariso folder. 

```
# single user run
# This will pick one user from the users.csv and run the test 
locust -H https://yourhost.xyz.com -u 1 --processes 1 --iteration=1 -f scenarios/st_runsleep01.py --only-summary --csv results/st_runsleep01 --headless

Note: The --headless option here is not a Playwright headless option mentioned above, 
but this is a Locust headless option to run without the Locust Web UI

# running locust with 3 users and for 5 iterations
# This will pick 3 users from the users.csv and run the test
# 3 users running 5 iterations will require you to at least have 15 users in your users.csv file

locust -H https://yourhost.xyz.com --u 3  --processes 3 --iteration=5 -f scenarios/st_runsleep01.py --only-summary --csv results/st_runsleep01 --headless

```

Start the test. You should see the tests progressing.  

For more locust options, refer to the following link: 
https://docs.locust.io/en/stable/quickstart.html#direct-command-line-usage-headless
