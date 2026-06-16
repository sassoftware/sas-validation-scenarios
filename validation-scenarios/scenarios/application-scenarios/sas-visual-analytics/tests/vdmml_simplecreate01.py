# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
# Header verification comment inserted

from common_epu import EnhancedPlaywrightUser, perf, txn

import asyncio
from playwright.async_api import expect
from locust import task
from locust_plugins.users.playwright import PageWithRetry, pw, PlaywrightUser# type: ignore
from playwright.async_api import Page
import datetime

from events import *
from auth import *
from exception import *
import traceback
import logging
from locust import runners


DEBUGGING = False
####################################################
#Function wait_for_job_completion
#Click on an object
#Listen for responses that contains "/reportData/jobs"
#Wait until jobs are completed.
####################################################


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


class vdmml_simplecreate01(EnhancedPlaywrightUser):
#    PlaywrightUser.headless=False
    # (optional) override defaults for EnhancedPlaywrightUser "global" member variables here; TIP: ctrl+click on "EnhancedPlaywrightUser" in the class definition line to see full list of member variables
    # PWTRACE = False
    # ABORT_ITERATION_WHEN_TXN_FAILS = False
    #--------------------------------------------------#
    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    

    async def add_roles(user, page: PageWithRetry,type):
            print("INFO: Adding roles")
            #Wait to be visible and then click
            #Not always visible- check if the message is there. If Roles is shown, click on Resppnse
            #Otherwise click on Roles
            data_roles_text = page.get_by_text("Data Roles")
            if await data_roles_text.is_visible():
                print("INFO: Data Roles is visible")
            else:
                print("INFO: Data Roles is not visible")
                roles = page.locator('div.sas_components-TabBar-__internal__-Tab_tab-inner:has-text("Roles")')
                await expect(roles).to_be_visible(timeout=user.INTERACTION_TIMEOUT)
                await roles.click(timeout=user.INTERACTION_TIMEOUT)
            await asyncio.sleep(1)    
            #Select Response
            print("Selecting Response")
            await page.get_by_text("Response").click(timeout=user.INTERACTION_TIMEOUT)
            await page.get_by_text("new_target - 2").click(timeout=user.INTERACTION_TIMEOUT)
            #Options
            await asyncio.sleep(1)
            options = page.locator('div.sas_components-TabBar-__internal__-Tab_tab-inner:has-text("Options")')
            await expect(options).to_be_visible(timeout=user.INTERACTION_TIMEOUT)
            await options.click(timeout=user.INTERACTION_TIMEOUT)
            await asyncio.sleep(1)
            #standardization - only for Neural Network
            if type == "Neural":
                print("Selecting standardization")
                standardization = page.get_by_role("combobox", name="Standardization:").locator("svg")
                await expect(standardization).to_be_visible( timeout=user.INTERACTION_TIMEOUT )
                await standardization.click(timeout=user.INTERACTION_TIMEOUT)
                await asyncio.sleep(1)
                await page.get_by_text("Standard deviation", exact=True).click( timeout=user.INTERACTION_TIMEOUT )

            #Event Level - Drop down
            await asyncio.sleep(0.05)
            print("Selecting Event Level")
            # Click on the combobox or dropdown showing "(none selected)"
            event = page.get_by_role("combobox", name="Event level:").locator("svg")
            await expect(event).to_be_visible( timeout=user.INTERACTION_TIMEOUT )
            await event.click(timeout=user.INTERACTION_TIMEOUT)
            await asyncio.sleep(1)
            await page.get_by_text("1", exact=True).click( timeout=user.INTERACTION_TIMEOUT )

            #Click on Roles
            roles = page.locator('div.sas_components-TabBar-__internal__-Tab_tab-inner:has-text("Roles")')
            await asyncio.sleep(1)
            await expect(roles).to_be_visible(timeout=user.INTERACTION_TIMEOUT)
            await roles.click(timeout=user.INTERACTION_TIMEOUT)
            #Add Predictors
            print("Selecting Predictors")
            await page.get_by_text("Predictors").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_role("textbox", name="Filter").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_role("textbox", name="Filter").fill("IN")
            await page.get_by_role("dialog", name="Add Data Items").locator("a").click( timeout=user.INTERACTION_TIMEOUT )
            await asyncio.sleep(1)
            print("INFO: add_roles finished")	  
 
    #--------------------------------------------------#
    @task # type: ignore
    @pw
    @perf

    async def Task01(user, page: PageWithRetry):
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
              #await ldap_auth(page, "rdtest0002", "good2go")
              user.logger.info(f"Authentication Successful")
            except:
              await exception_handling("Failed to Authenticate", user)
              raise

        async with event(user, "01-Navigating to SAS Visual Analytics"):
            user.logger.info(f"Navigating to SAS Visual Analytics")
            await page.goto("/SASVisualAnalytics" , timeout=60000)
            timestamp = random.randint(1000, 9999)
       
        await page.wait_for_timeout(3_000)
        ########################################################################################################    

        async with txn(user, "02.Select_Data"):  
            print("Transaction: 02.Select_Data")
            new_report  = page.get_by_test_id("newReportFromHome")  
            await expect(new_report).to_be_visible(timeout=user.INTERACTION_TIMEOUT)
            await new_report.click(timeout=user.INTERACTION_TIMEOUT)
            await page.get_by_role("button", name="Add data").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_placeholder("Search all data").fill("GENDATA01M_01_VISUAL_0101_VARS")
            await page.get_by_role("button", name="Start search").click(timeout=user.INTERACTION_TIMEOUT)
            #CLick on the table (It should be only 1 result)
            # 2025.03 Identifier
            #await page.get_by_test_id("row-0-checkbox").click( timeout=user.INTERACTION_TIMEOUT )
            # 2025.05 onwards Identifier 
            await page.get_by_role("gridcell", name="Select row").locator("div").first.click( timeout=user.INTERACTION_TIMEOUT )
        await page.wait_for_timeout(3_000)    
        ########################################################################################################        

        async with txn(user, "03.Add_Data"):  
            print("Transaction: 03.Add_Data")
            #CLick in the button "Add"
            await page.get_by_role("button", name="Add", exact=True).click( timeout=user.INTERACTION_TIMEOUT )   
            #wait until new_target2 exists
            label = page.get_by_text("new_target - 2", exact=True)
            await label.wait_for(state="visible", timeout=user.INTERACTION_TIMEOUT)
            #Wait until Add objects exist
            await page.get_by_test_id("appLayout-objects-tabItem").locator("svg").wait_for(timeout=user.INTERACTION_TIMEOUT)
        ########################################################################################################    

        async with txn(user, "04.Add_GB"):        
            print("Transaction: 04.Add_GB")
            #Click on Objects to add Gradient Boosting
            await page.get_by_test_id("appLayout-objects-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
            #Gradient Boosting
            await page.get_by_test_id("searchField-searchInput-input").fill("gradient boosting")
            await page.wait_for_timeout(1_000)
            await page.get_by_text("Gradient boosting").dblclick(timeout=user.INTERACTION_TIMEOUT)

        ########################################################################################################    
        async with txn(user, "05.GB-Add_roles"):
            print("Transaction: 05.GB-Add_roles")
            await user.add_roles(page,"GB")
           
        ########################################################################################################    

        async with txn(user, "06.GB-Execution"): 
            print("Transaction: 06.GB-Execution")
            start = datetime.now()  
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT,'click', "None")
            end = datetime.now()
            txn_duration = end - start
            print(f"Total Elapsed Time: Transaction 06.GB-Execution {txn_duration}")

        await page.wait_for_timeout(3000)
        ########################################################################################################    

        async with txn(user, "07.Add_Forest"):  
            print("Transaction: 07.Add_Forest")  
            print("Closing Object menu for Gradient Boosting")
            #Close GB
            await page.get_by_role("button", name="Object menu for Gradient").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_text("Delete").click()
            await expect(page.get_by_text("Design a Report")).to_be_visible( timeout=user.TXNTIMEOUT )
            #Click on Objects to add Forest
            await page.get_by_test_id("appLayout-objects-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_test_id("searchField-searchInput-input").fill("Forest")
            await page.wait_for_timeout(1_000)
            await page.get_by_text("Forest").dblclick(timeout=user.INTERACTION_TIMEOUT)
        ######################################################################################################## 

        async with txn(user, "08.Forest-Add_roles"):
            print("Transaction: 08.Forest-Add_roles")
            await user.add_roles(page,"Forest")
                       
         
        ########################################################################################################    

        async with txn(user, "09.Forest-Execution"): 
            print("Transaction: 09.Forest-Execution")
            start = datetime.now()  
            locator = page.locator('button:has-text("Apply")')
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT,'click', "None")
            end = datetime.now()
            txn_duration = end - start
            print(f"Total Elapsed Time: Transaction 09. Forest-Execution {txn_duration}")
        await page.wait_for_timeout(3000)
        ########################################################################################################

        async with txn(user, "10.Add_Neural_Network"):   
            print("Transaction: 10.Add_Neural_Network")
            print("Closing Object menu for Forest") 
            #Close GB
            await page.get_by_role("button", name="Object menu for Forest").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_text("Delete").click()
            await expect(page.get_by_text("Design a Report")).to_be_visible( timeout=user.TXNTIMEOUT )
            #Click on Objects to add Forest
            await page.get_by_test_id("appLayout-objects-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_test_id("searchField-searchInput-input").fill("Neural")
            await page.wait_for_timeout(1_000)
            await page.get_by_text("Neural network").dblclick( timeout=user.INTERACTION_TIMEOUT )
            
        ########################################################################################################
        async with txn(user, "11.Neural_Network-Addroles"):
            print("Transaction: 11.Neural_Network-Addroles")
            await user.add_roles(page,"Neural")
            
        ########################################################################################################    

        async with txn(user, "12.Neural_Network-Execution"): 
            print("Transaction: 12. Neural Network-Execution")
            start = datetime.now()  
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT,'click', "None")
            end = datetime.now()
            txn_duration = end - start
            print(f"Total Elapsed Time: Transaction 12. Neural Network-Execution {txn_duration}")
        await page.wait_for_timeout(3000)    
        
        ########################################################################################################    
        async with txn(user, "13.Add_SVM"):    
            print("Transaction: 13.Add_SVM")
            print("Closing Object menu for Neural Network")
            #Close GB
            await page.get_by_role("button", name="Object menu for Neural").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_text("Delete").click()
            await expect(page.get_by_text("Design a Report")).to_be_visible( timeout=user.TXNTIMEOUT )
            await asyncio.sleep(1)
            #Click on Objects to add Forest
            await page.get_by_test_id("appLayout-objects-tabItem").locator("svg").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_test_id("searchField-searchInput-input").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_test_id("searchField-searchInput-input").fill("vector machine")
            await page.get_by_text("Support vector machine").dblclick( timeout=user.INTERACTION_TIMEOUT )
            await asyncio.sleep(1)

        ########################################################################################################   

        async with txn(user, "14.SVM_Add_roles"):
            print("Transaction: 14.SVM_Add_roles")    
            await user.add_roles(page,"SVM")
           
        ########################################################################################################    

        async with txn(user, "15.SVM-Execution"): 
            print("Transaction: 15.SVM-Execution")
            start = datetime.now()  
            await asyncio.sleep(1)
            locator = page.get_by_role("button", name="Apply")
            duration = await wait_for_job_completion(page, locator, user.INTERACTION_TIMEOUT,'click', "None")
            end = datetime.now()
            txn_duration = end - start
            print(f"Total Elapsed Time: 15.SVM-Execution {txn_duration}")
        await page.wait_for_timeout(3000)  

        ########################################################################################################
        async with txn(user, "16.Delete_SVM"):    
            print("Transaction: 16.Delete_SVM")
            #Close GB
            await page.get_by_role("button", name="Object menu for Support").click( timeout=user.INTERACTION_TIMEOUT )
            await page.get_by_text("Delete").click()
            await expect(page.get_by_text("Design a Report")).to_be_visible( timeout=user.TXNTIMEOUT )
        await asyncio.sleep(1)     


        
        ########################################################################################################    
        async with txn(user, "17.SignOut"): 
           print("Transaction: 17.Sign Out")
           await page.get_by_test_id("VAAppRootBanner-options").click( timeout=user.INTERACTION_TIMEOUT )
           await page.get_by_test_id("VAAppRootBanner-signout-text").click( timeout=user.INTERACTION_TIMEOUT )
           await page.get_by_role("button", name="Discard and exit").click( timeout=user.INTERACTION_TIMEOUT )    
           #await expect(page.locator('h3:has-text("You have signed out.")')).to_be_visible(timeout=user.TXNTIMEOUT)
           await expect(page.get_by_role("heading", name="You have signed out.")).to_be_visible( timeout=user.TXNTIMEOUT)
        await asyncio.sleep(1)


    #--------------------------------------------------#
    @pw
    async def on_stop(user, page: Page):

        user.print(f"on_stop TOP")
        # Proper way to add a "think time" to your script because this does not block the Playwright event loop (which time.sleep() does), so the browser can still handle other tasks during the "think time"
        await asyncio.sleep(         user.END_OF_TEST_PAUSE_SEC*1000/2 ) # This WILL be included in a transaction timing
        #await page.wait_for_timeout( user.END_OF_TEST_PAUSE_SEC*1000/2 ) # This will NOT be included in a transaction timing
        user.print(f"on_stop BOT")
