# **Scenario Development**

This section describes how to develop new scenarios and tests using Playwright and prepare them for Locust-based execution in this sas-validation-scenarios framework.

Make sure you have prepared your environment folliwng the steps here in [Preparing your Client](https://gitlab.sas.com/aat/sas-validation-scenarios/-/tree/main?ref_type=heads#preparing-your-client)
Specifically this section where you re-activate your python environment:

`source $VALIDATION_PROJECT_PATH/bin/activate`

## Playwright Codegen

Playwright comes with the ability to generate tests out of the box and is a great way to quickly get started with testing. It will open two windows, a browser window where you interact with the website you wish to test and the Playwright Inspector window where you can record your tests, copy the tests, clear your tests as well as change the language of your tests.
For recording tests and generating locators, refer the this [Generating Tests](https://playwright.dev/python/docs/codegen-intro) section of the [Playwright for python](https://playwright.dev/python/docs/intro) documentation. 

Once you have installed playwright for python, the associated modules adn everything you need from the links above, bring up laywright codegen and record a simple flow. 
Such as open you Viya web application, log in and goru a simple flow. 
You should see the code it records in the codegen window. 
Save this code in a file called recordertest.py and we will come back to this code in a future step. 

If you are new to codegen and need more help, there are many youtube videos explaining this process. 
Note: Playwright is a browser automation tool designed for web applications. 


## Common Modules

We have a set of common modules available which simplifies and unifies the common tasks of managing users, user events, authentication to /SASLogon, exception handling etc. These common libraries are growing and more will be added as the needs come up.
Our guidelines are that you use these common modules we have developed rather than create your own. 
These common modules reside in the framework/exection/common folder of the sas-validation-scenarios.

Basically we want to import the following libraries:
from events import *
from auth import *
from exception import *

##### events.py

Locust comes with a number of built in event hooks that can be used to extend Locust in different ways. There are built-in event hooks to add this functionality like init and quitting which can be used when running the locustfile using locust command.  Locust provides powerful event hooks, such as test_start and test_stop, to execute custom logic before and after a load test begins or ends. These events allow you to implement setup and teardown operations at the test level, which applies to the entire test run rather than individual users.

And the start of the task in your locust script would look like this:

    async with event(self, "01: Starting New logonoff tests"):



##### auth.py

The auth module in the common module takes care of the authentication to SAS Viya web applications.

Currently we have support for ldap and auth.sas.com used for engage envirponments. 

##### exception.py

Defines custom exception handling  in case of failure.

#### Authenticating to /SASLogon

We designed our framework in such a way that when we log into a SAS Viya web application, we first authenticate to /SASLogon, sign in using the userid and password and finish login. After a successful login, we access the application.

Here is an example of a SAS Studio scenario:  

```
from events import *
from auth import *
from exception import *

async with event(self, "01: Starting New logonoff tests"):
    try:
       self.logger.info(f"Authenticating to SASLogon")
       await ldap_auth(page, user, password)
       self.logger.info(f"Authentication Successful")
   except:
      await exception_handling("Failed to Authenticate", user)
   raise

async with event(self, "01: Navigating to SAS Studio"):
      self.logger.info(f"Navigating to SAS Studio")
      await page.goto("/SASStudio" , timeout=60000)
```

#### Exception Handling

We recommend that every block of code (in @task) should have a good exception handling mechanism such as this:

```
   try:
       self.logger.info(f"Authenticating to SASLogon")
       await ldap_auth(page, user, password)
       self.logger.info(f"Authentication Successful")
   except:
      await exception_handling("Failed to Authenticate", user)
   raise
```

---

## 📁 1. Creating a New Scenario

To start creating new tests in this framework, first create a new folder inside the scenarios-development directory.

Name the folder meaningfully (e.g., aml-alert-creation).

Then, copy the example file test-development-template.py into this folder as a starting point for your test development.

**Example structure of scenario and tests:**

![worker-finished](framework/images/scenarios-development-structure.png)

💡 Note: In this example, there's only one test file, but a scenario folder can contain multiple test files.

---

### ✍️ 2. Write Your Test in Playwright

Once you've created the folder for your scenario, you can start writing your test.

The test-template.py file includes a predefined structure using special comment markers. Do not change these markers, as they are required for automated conversion:

- `###!DEV_TEST` / `###$!DEV_TEST` – code used during Playwright script development and for single user run
- `###!FRAMEWORK_TEST` / `###$!FRAMEWORK_TEST` – code used in the final Locust version

There are two key sections you should edit while developing your test:

- `###!DEV_CONVERT_PARAMETERS` – for defining reusable test parameters
- `###!DEV_CONVERT_EVENTS` – for defining test methods. These methods will be wrapped in Locust event() calls. The second argument of the method will be the event name.

Each test method should include a logger line as the **first statement** inside the function:

```python
self.logger.info("02: Log in to SAS Visual Investigator")
```

because later it will be used as a event name that will appear in outputs from the thest

```python
async with event(self, "02: Log in to SAS Visual Investigator"):
```

---

### ✅ 3. Run and Verify the Test Interactively

After writing your test, run it in headed browser mode to verify it behaves as expected:

```bash
python3 test-development-template.py
```

✔️ What to Check?

- The test executes without errors or unhandled exceptions

- Each step is correctly logged using self.logger.info(...)

- All UI interactions (clicks, navigation, expectations) are correct

- You have added time.sleep(...) only if necessary for stability

- Each method inside the ###!DEV_CONVERT_EVENTS block begins with a logger line
  (this is crucial for automated event() conversion in the next step)

If you confirm that script is working correctly then you can go to the next step and convert this script to Locust version

---

### ✅ 4: Convert the Scenario to Locust Framework Format

When your test is working interactively, convert it to Locust format using the following command:

```bash
python3 scenario_generation_script.py <your-folder-name>
```

Example:

```bash
python3 scenario_generation_script.py aml-alert-open
```

🔧 What This Script Does

- Removes all ###!DEV_TEST ... ###$!DEV_TEST blocks that are required only for test development

- Uncomments lines in ###!FRAMEWORK_TEST ... ###$!FRAMEWORK_TEST that are required in Locust version of the script

- Converts parameters like self.TIMEOUT_SHORT to direct class attributes

- Wraps each method in ###!DEV_CONVERT_EVENTS with:

```python
async with event(self, "<Logger message here>"):
```

- Creates two output folders:

  ../scenarios/<your-folder-name>/tests/ — test in Locust version

  ../scenarios/<your-folder-name>/tests-single-user/ — version with headless=True for recording and pw-trace creation

- Generates a workload definition file:

  ../workload-definitions/<your-folder-name>-wrkld-def.yaml

---

### ✅ 5: Running a test

After running scenario_generation_script.py you can run your script in single user or locust mode.

Instruction how to run a test can be found in **Steps to run various Scenarios** chapter
