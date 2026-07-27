# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from common_epu import EnhancedPlaywrightUser, perf, txn

import asyncio
from playwright.async_api import expect
from locust import task
from locust_plugins.users.playwright import PageWithRetry, pw, PlaywrightUser # type: ignore
from playwright.async_api import Page
import datetime

from events import *
from auth import *
from exception import *
import traceback
import logging
from locust import runners

DEBUGGING = True

async def wait_for_job_completion(
	page,
	locator,
	INTERACTION_TIMEOUT,
	action='click',
	key="None",
	timeout_seconds=3600,
	network_idle_time=1,  
):
	start = datetime.now()
	print("\n################# INFO: START wait_for_jobs_to_complete #################")
	print("Start Time:", start.strftime("%Y-%m-%d %H:%M:%S"))
	job_detail_responses = []
	job_states = {}
	processed_responses = set()
	completed_jobs = {}

	started_requests = set()
	last_request_time = None

	def on_request(request):
		nonlocal last_request_time
		started_requests.add(request)
		last_request_time = datetime.now()

	def on_request_done(request):
		nonlocal last_request_time
		started_requests.discard(request)
		last_request_time = datetime.now()

	def handle_response(response):
		url = response.url
		if "/reportData/jobs/" in url or "/reportData/jobs?" in url:
			job_detail_responses.append(response)

	context = page.context
	context.on("response", handle_response)
	context.on("request", on_request)
	context.on("requestfinished", on_request_done)
	context.on("requestfailed", on_request_done)

	print("INFO: ACTION:", action)
	#Only 'click' and 'press' with 'Enter' key are supporte
	if action.lower() == "click":
		action_exec = datetime.now()
		await locator.click(timeout=INTERACTION_TIMEOUT)
	elif action.lower() == "press" and key == "Enter":
		action_exec = datetime.now()
		await locator.press("Enter")
	else:
		print("Only 'click' and 'press' with 'Enter' key are supported.")
		context.remove_listener("response", handle_response)
		context.remove_listener("request", on_request)
		context.remove_listener("requestfinished", on_request_done)
		context.remove_listener("requestfailed", on_request_done)
		return None

	sleep_time = 0.5
	waited = 0
	idle_start = None
	while waited < timeout_seconds:
		await asyncio.sleep(sleep_time)
		waited += sleep_time
		new_job_or_state = False
		for response in list(job_detail_responses):
			if response not in processed_responses:
				try:
					data = await response.json()
					job_id = data.get("id")
					state = data.get("state")
					dt_completed = data.get("completedTimeStamp")
					dt_created = data.get("creationTimeStamp")

					now = datetime.now()
					if job_id:
						if state == "completed" and job_id not in completed_jobs:
							print(f"Job {job_id} CREATED at : {dt_created}")
							print(f"Job {job_id} COMPLETED at : {dt_completed} (local: {now.strftime('%Y-%m-%d %H:%M:%S')})")
							completed_jobs[job_id] = now
							new_job_or_state = True
						job_states[job_id] = state
				except Exception as e:
					print("Error processing job:", str(e))
				finally:
					processed_responses.add(response)

		#  Only exit if all jobs completed and network is idle
		all_jobs_completed = job_states and all(state == "completed" for state in job_states.values())
		if all_jobs_completed and not started_requests:
			if idle_start is None:
				idle_start = datetime.now()
				print("All jobs completed and network is idle")
			else:
				idle_duration = (datetime.now() - idle_start).total_seconds()
				if idle_duration >= network_idle_time:
					print(f"Network idle for {network_idle_time} seconds. All jobs completed. ")
					break
		else:
			#network busy
			idle_start = None  
	else:
		print("Timed out waiting for jobs")

	await asyncio.sleep(2)
	if completed_jobs:
		latest_job_id, latest_time = max(completed_jobs.items(), key=lambda item: item[1])
	else:
		print("No jobs were completed.")

	context.remove_listener("response", handle_response)
	context.remove_listener("request", on_request)
	context.remove_listener("requestfinished", on_request_done)
	context.remove_listener("requestfailed", on_request_done)
	print(f"Action started at {action_exec}")
	print(f"Latest job was completed at {latest_time}")
	action_execution = latest_time - action_exec
	print("End Time from when the action (click or Enter) started to when the last job was completed:", action_execution.total_seconds())

	end = datetime.now()
	duration = end - start
	print("End Time:", end.strftime("%Y-%m-%d %H:%M:%S"))
	print(f"Function Elapsed time : {duration.total_seconds()}")
	print("################# INFO: END wait_for_jobs_to_complete #################\n")
	return duration.total_seconds()

async def add_input_table(user, page):
    await page.get_by_test_id("newReportFromHome").click( timeout=user.INTERACTION_TIMEOUT )
    await asyncio.sleep(1)
    await page.get_by_role("button", name="Data source menu").click( timeout=user.INTERACTION_TIMEOUT )
    await asyncio.sleep(1)
    await page.get_by_test_id("dataSourceMenu-addDataSource-text").click( timeout=user.INTERACTION_TIMEOUT )
    await asyncio.sleep(1)
    await page.get_by_role("textbox", name="Search all data").click( timeout=user.INTERACTION_TIMEOUT )
    await asyncio.sleep(1)
    await page.get_by_role("textbox", name="Search all data").type("REG_SIMTBL_VSBENCH_200M", delay=400)
    await page.get_by_role("textbox", name="Search all data").press("Enter")
    await asyncio.sleep(1)
    await page.get_by_test_id("row-0-checkbox").click( timeout=user.INTERACTION_TIMEOUT )
    
    async with txn(user, "02-AddInputTable"):
        print("Transaction: 02-AddInputTable")
        await page.get_by_role("button", name="Add", exact=True).click( timeout=user.INTERACTION_TIMEOUT )
        await expect(page.get_by_text("New data item", exact=True)).to_be_visible( timeout=user.TXNTIMEOUT )

class vs_simplecreate01(EnhancedPlaywrightUser):
    # PlaywrightUser.headless = False
    # (optional) override defaults for EnhancedPlaywrightUser "global" member variables here; TIP: ctrl+click on "EnhancedPlaywrightUser" in the class definition line to see full list of member variables
    # PWTRACE = False
    # ABORT_ITERATION_WHEN_TXN_FAILS = False
    #--------------------------------------------------#

    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    #--------------------------------------------------#
    @task # type: ignore
    @pw
    async def Task01(user, page: PageWithRetry):
        """ This is a python docstring where you can describe what this "task" does. This description will show up in VSCode as a tooltip on mouse hover. """
        #===-===#===-===#===-===#===-===#===-===#===-===#===-===#===-===#===-===#===-===# script core TOP
        if len(usernames) == 0:
            user.logger.info(f"No more users in the list, exiting as success")
            exit(0)


        user_ray = usernames.pop(random.randrange(len(usernames)))
        userin = user_ray[0]
        password = user_ray[1]  
    
        async with event(user, "00-Starting New tests"):
            try:  
              user.logger.info(f"Authenticating to SASLogon")
              await ldap_auth(page, userin, password)
              user.logger.info(f"Authentication Successful")
            except:
              await exception_handling("Failed to Authenticate", user)
              raise

        async with event(user, "01-Navigating to SAS Visual Analytics"):
            user.logger.info(f"Navigating to SAS Visual Analytics")
            await page.goto("/SASVisualAnalytics" , timeout=60000)
            timestamp = random.randint(1000, 9999)
        
        ########################################################################################
        # LINEAR REGRESSION
        ########################################################################################      

        await asyncio.sleep(3)
        await add_input_table(user, page)
        user.logger.info(f"Regselect: Input Table Added.")
        
        await asyncio.sleep(3)
        await page.get_by_test_id("appLayout-objects-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("searchField-searchInput-input").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("searchField-searchInput-input").type("linear regression", delay=400)
        await asyncio.sleep(1)
        await page.get_by_test_id("objectsPane-linearRegressionContainer").get_by_test_id("objectsPane-elementsTreeTable-cellContent").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("checkbox",name="Linear regression").dblclick(timeout=user.INTERACTION_TIMEOUT)
        await asyncio.sleep(3)
        data_roles_text = page.get_by_text("Data Roles")
        if await data_roles_text.is_visible():
            print("Data Roles")
        else:
            print("No Data Roles")
            roles_ = page.locator('div.sas_components-TabBar-__internal__-Tab_tab-inner:has-text("Roles")')
            await expect(roles_).to_be_visible(timeout=user.INTERACTION_TIMEOUT)
            await roles_.click(timeout=user.INTERACTION_TIMEOUT)

        await asyncio.sleep(3)
        #await page.locator("xpath=//*[@id='tree-node-sas_RC-treeTable-3-response']").click()
        await page.get_by_text("Response").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("y", delay=400)
        await asyncio.sleep(1)

        async with txn(user, "03-regselect: AddResponseVariable"):
            print("Transaction: 03-regselect: AddResponseVariable")
            await page.get_by_role("gridcell", name="Measure y", exact=True).locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
            await page.wait_for_load_state("networkidle")
            user.logger.info(f"Regselect: Response Variable Added.")
        
        await asyncio.sleep(3)
        await page.get_by_text("Continuous effects").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("x0", delay=400)
        await asyncio.sleep(1)
        await page.get_by_role("dialog", name="Add Data Items").locator("a").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        
        async with txn(user, "04-regselect: AddContinuousVariables"):
            print("Transaction: 04-regselect: AddContinuousVariables")
            #await page.get_by_role("button", name="Apply").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Regselect: Continous Variables Added.")
        
        await asyncio.sleep(1)
        await page.get_by_text("Classification effects").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("class", delay=400)
        await asyncio.sleep(1)
        await page.get_by_role("dialog", name="Add Data Items").locator("a").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "05-regselect: AddClassificationVariables"):
            print("Transaction: 05-regselect: AddClassificationVariables")
            #await page.get_by_role("button", name="Apply").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Regselect: Classification Variables Added.")

        await asyncio.sleep(3)
        await page.get_by_test_id("appLayout-options-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "06-regselect: SelectInformationMissingness"):
            print("Transaction: 06-regselect: SelectInformationMissingness")
            #await page.get_by_test_id("optionsPane-INCLUDE_MISSING_FIELD-checkbox").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_test_id("optionsPane-INCLUDE_MISSING_FIELD-checkbox")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Regselect: Information Missingness Option Selected.")
        
        await asyncio.sleep(3)
        await page.get_by_test_id("optionsPane-VARIABLE_SELECTION_TYPE_FIELD-value").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "07-regselect: SelectStepwise"):
            print("Transaction: 07-regselect: SelectStepwise")
            #await page.get_by_test_id("optionsPane-VARIABLE_SELECTION_TYPE_FIELD-list-listItem-3-text").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_test_id("optionsPane-VARIABLE_SELECTION_TYPE_FIELD-list-listItem-3-text")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Regselect: Stepwise Option Selected.")
        
        await asyncio.sleep(3)
        await page.get_by_test_id("appMenuButton-button").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("appMenu-closeReport-text").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("button", name="Don't save").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        ########################################################################################
        # LOGISTIC REGRESSION
        ########################################################################################
        await asyncio.sleep(3)
        await add_input_table(user, page)
        user.logger.info(f"Logselect: Input Table Added.")

        await asyncio.sleep(3)
        await page.get_by_test_id("appLayout-objects-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("searchField-searchInput-input").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("searchField-searchInput-input").type("logistic regression", delay=400)
        await asyncio.sleep(1)
        await page.get_by_test_id("objectsPane-logisticRegressionContainer").get_by_test_id("objectsPane-elementsTreeTable-cellContent").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        #await page.locator("xpath=//*[@id='tree-node-sas_RC-treeTable-1-logisticRegressionContainer']").dblclick( timeout=user.INTERACTION_TIMEOUT )
        await page.get_by_text("Logistic regression").first.dblclick( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(2)
        data_roles_text = page.get_by_text("Data Roles")
        if await data_roles_text.is_visible():
            print("Data Roles")
        else:
            print("No Data Roles")
            roles_ = page.locator('div.sas_components-TabBar-__internal__-Tab_tab-inner:has-text("Roles")')
            await expect(roles_).to_be_visible(timeout=user.INTERACTION_TIMEOUT)
            await roles_.click(timeout=user.INTERACTION_TIMEOUT)
        
        await asyncio.sleep(1)
        await page.get_by_text("Response").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("char", delay=400)
        await asyncio.sleep(1)

        async with txn(user, "08-logselect: AddResponseVariable"):
            print("Transaction: 08-logselect: AddResponseVariable")
            await page.get_by_text("char_ybin -").click( timeout=user.INTERACTION_TIMEOUT )
            await page.wait_for_load_state("networkidle")
            user.logger.info(f"Logselect: Response Variable Added.")

        await asyncio.sleep(3)    
        await page.get_by_text("Continuous effects").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("x0", delay=400)
        await asyncio.sleep(1)
        await page.get_by_role("dialog", name="Add Data Items").locator("a").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "09-logselect: AddContinuousVariables"):
            print("Transaction: 09-logselect: AddContinuousVariables")
            #await page.get_by_role("button", name="Apply").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Logselect: Continuous Variables Added.")
        
        await asyncio.sleep(3)
        await page.get_by_text("Classification effects").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("class", delay=400)
        await asyncio.sleep(1)
        await page.get_by_role("dialog", name="Add Data Items").locator("a").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "10-logselect: AddClassificationVariables"):
            print("Transaction: 10-logselect: AddClassificationVariables")
            #await page.get_by_role("button", name="Apply").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Logselect: Classification Variables Added.")
        
        await asyncio.sleep(3)
        await page.get_by_test_id("appLayout-options-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "11-logselect: SelectInformationMissingness"):
            print("Transaction: 11-logselect: SelectInformationMissingness")
            #await page.get_by_test_id("optionsPane-INCLUDE_MISSING_FIELD-checkbox").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_test_id("optionsPane-INCLUDE_MISSING_FIELD-checkbox")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Logselect: Information Missingness Option Selected.")
        
        await asyncio.sleep(3)
        await page.get_by_test_id("optionsPane-VARIABLE_SELECTION_TYPE_FIELD-value").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "12-logselect: SelectFastBackward"):
            print("Transaction: 12-logselect: SelectFastBackward")
            #await page.get_by_test_id("optionsPane-VARIABLE_SELECTION_TYPE_FIELD-list-listItem-3-text").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_test_id("optionsPane-VARIABLE_SELECTION_TYPE_FIELD-list-listItem-3-text")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Logselect: FastBackward Option Selected.")
        
        await asyncio.sleep(3)
        await page.get_by_test_id("appMenuButton-button").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("appMenu-closeReport-text").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("button", name="Don't save").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        ########################################################################################
        # GENERALIZED LINEAR MODEL
        ########################################################################################

        await asyncio.sleep(3)
        await add_input_table(user, page)
        user.logger.info(f"Glmselect: Input Table Added.")
        
        await asyncio.sleep(3)
        await page.get_by_test_id("appLayout-objects-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("searchField-searchInput-input").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("searchField-searchInput-input").type("generalized linear model", delay=400)
        await asyncio.sleep(1)
        await asyncio.sleep(1)
        await page.get_by_test_id("objectsPane-glmContainer").get_by_test_id("objectsPane-elementsTreeTable-cellContent").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_text("Generalized linear model").dblclick( timeout=user.INTERACTION_TIMEOUT )
        #await page.locator("xpath=//*[@id='tree-node-sas_RC-treeTable-1-glmContainer']").dblclick( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(3)

        #await page.get_by_test_id("appLayout-roles-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
        data_roles_text = page.get_by_text("Data Roles")
        if await data_roles_text.is_visible():
            print("Data Roles")
        else:
            print("No Data Roles")
            roles_ = page.locator('div.sas_components-TabBar-__internal__-Tab_tab-inner:has-text("Roles")')
            await expect(roles_).to_be_visible(timeout=user.INTERACTION_TIMEOUT)
            await roles_.click(timeout=user.INTERACTION_TIMEOUT)

        await asyncio.sleep(1)
        await page.get_by_text("Response").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("cls6", delay=400)
        await asyncio.sleep(1)

        async with txn(user, "13-glmselect: AddResponseVariable"):
            print("Transaction: 13-glmselect: AddResponseVariable")
            await page.get_by_text("cls6").click( timeout=user.INTERACTION_TIMEOUT )
            await page.wait_for_load_state("networkidle")
            user.logger.info(f"Glmselect: Response Variable Added.")

        await asyncio.sleep(3)
        await page.get_by_test_id("appLayout-options-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("optionsPane-DISTRIBUTION_FIELD-value").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "14-glmselect: SelectPoissonOption"):
            print("Transaction: 14-glmselect: SelectPoissonOption")
            await page.get_by_test_id("optionsPane-DISTRIBUTION_FIELD-list-listItem-8-text").click( timeout=user.INTERACTION_TIMEOUT )
            await page.wait_for_load_state("networkidle")
            user.logger.info(f"Glmselect: Poisson Option Selected.")
        
        await asyncio.sleep(3)
        await page.get_by_test_id("appLayout-roles-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_text("Continuous effects").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("x0",delay=400)
        await asyncio.sleep(1)
        await page.get_by_role("dialog", name="Add Data Items").locator("a").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        
        async with txn(user, "15-glmselect: AddContinuousVariables"):
            print("Transaction: 15-glmselect: AddContinuousVariables")
            #await page.get_by_role("button", name="Apply").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Glmselect: Continuous Variables Added.")

        await asyncio.sleep(3)
        await page.get_by_text("Classification effects").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("class", delay=400)
        await asyncio.sleep(1)
        await page.get_by_role("dialog", name="Add Data Items").locator("a").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "16-glmselect: AddClassificationVariables"):
            print("Transaction: 16-glmselect: AddClassificationVariables")
            #await page.get_by_role("button", name="Apply").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Glmselect: Classification Variables Added.")

        await asyncio.sleep(3)
        await page.get_by_text("Response").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_text("Continuous effects").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_text("Classification effects").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_text("Offset").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("textbox", name="Filter").type("log", delay=400)
        await asyncio.sleep(1)

        async with txn(user, "17-glmselect: AddOffsetVariable"):
            print("Transaction: 17-glmselect: AddOffsetVariable")
            #await page.get_by_text("logcls7_offset").click( timeout=user.INTERACTION_TIMEOUT )
            locator = page.get_by_text("logcls7_offset")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT)
            print(duration)
            user.logger.info(f"Glmselect: Offset Variable Added.")

        await asyncio.sleep(3)
        await page.get_by_test_id("appMenuButton-button").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_test_id("appMenu-closeReport-text").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        await page.get_by_role("button", name="Don't save").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)
        
        await asyncio.sleep(1)
        await page.get_by_test_id("VAAppRootBanner-options").click( timeout=user.INTERACTION_TIMEOUT )
        await asyncio.sleep(1)

        async with txn(user, "27-SignOff"):
            print("Transaction: 27-SignOff")
            await page.get_by_test_id("VAAppRootBanner-signout-text").click( timeout=user.INTERACTION_TIMEOUT )
            #await expect(page.locator("//h3[ text() = 'You have signed out.' ]")).to_be_visible( timeout=user.TXNTIMEOUT )
            await expect(page.get_by_role("heading", name="You have signed out.")).to_be_visible( timeout=user.TXNTIMEOUT)
            user.logger.info(f"SignOff")
            
        await asyncio.sleep(3)
    #--------------------------------------------------#
