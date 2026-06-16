# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
# Header verification comment inserted

from events import *
from auth import *
from exception import *
from locust_plugins.users.playwright import PlaywrightUser, pw, event, PageWithRetry
import traceback
import asyncio
import logging
from locust import runners

class st_40nodesflow(PlaywrightUser):

    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    @task
    @pw
    async def test_st_40nodesflow(self, page: PageWithRetry):

        browser = self.browser
        context = self.browser_context

        page.set_default_timeout(timeout=self.TIMEOUT_LONG)
        if len(usernames) == 0:
            self.logger.info(f"No more users in the list, exiting as success")
            exit(0)

        user_ray = usernames.pop(random.randrange(len(usernames)))
        user = user_ray[0]
        password = user_ray[1]

        async with event(self, "01: Starting New SAS st_40nodesflow tests"):
          try:  
            self.logger.info(f"Authenticating to SASLogon")
            await ldap_auth(page, user, password)
            self.logger.info(f"Authentication Successful")
          except:
            await exception_handling("Failed to Authenticate", user)
            raise        

        async with event(self, "01: Navigating to SAS Studio"):
            self.logger.info(f"Navigating to SAS Studio")
            await page.goto("/SASStudio/" , timeout=60000)
            timestamp = random.randint(1000, 9999)
           
        async with event(self, "03: Creating SAS Studio compute Context"):
          try:  
            self.logger.info(f"Start: Creating Studio Compute Context")
            await page.get_by_test_id("appHeaderToolbar-new-button").click()
            await page.get_by_test_id("appHeaderToolbar-sascode-text").click()   
            await page.get_by_test_id("tab-group-bar-_root_").get_by_text("SAS Program.sas").click()
            await expect(page.get_by_test_id("appHeaderToolbar-studioActiveServerObjectMarker").locator("svg")).not_to_be_visible(timeout=60000)
            await expect(page.get_by_test_id("appHeaderToolbar-studioActiveServerButton")).to_be_visible(timeout=60000) 
            await page.get_by_test_id("tab-group-bar-_root_").get_by_text("SAS Program.sas").click()
            await expect(page.get_by_test_id("programViewPane-toolbar-runButton")).to_be_enabled(timeout=60000)
            self.logger.info(f"Finished Creating Studio Compute Context")
          except:
            await exception_handling("Failed to create compute context", user)
            raise

        async with event(self,"04: Run Data Flow"):
          try:
            self.logger.info(f"Starting to Run Data Flow")
            self.logger.info(f'Starting to open 40nodes.flw')
            await page.get_by_test_id("appHeaderToolbar-open").click()

            await page.get_by_role("button", name="SAS Folders SAS Content").dblclick()
            await page.get_by_test_id("explorer-dialog-folder-tree").get_by_text("SAS Content").dblclick()
            await page.get_by_test_id("member-list-grid-wrapper").get_by_text("Public").dblclick()
            await page.get_by_test_id("member-list-grid-wrapper").get_by_text("40nodes.flw").click()
            await page.get_by_test_id("file-folder-dialog-firstButton").click()
            self.logger.info(f"Finished opening 40nodes.flw program")
            self.logger.info(f"Data Flow: 40nodes.flw successfully opened")
            await page.get_by_test_id("tab-2").get_by_text("40nodes.flw").click()
            await page.get_by_test_id("flowtoolbar-runButton").click()
            self.logger.info(f"Clicked on Run to run the data flow")
            time.sleep(3)
            await expect(page.get_by_test_id("tab-2").get_by_label("Processing").locator("svg")).not_to_be_visible(timeout=500000)
            await expect(page.get_by_test_id("flowtoolbar-runButton")).to_be_visible(timeout=120000)
            self.logger.info(f"Data Flow progress bar is no longer visible")
            #await page.locator("iframe[title=\"SAS® Studio\"]").content_frame.get_by_role("tab", name="Submitted Code and Results").locator("div").nth(1).click()
            self.logger.info(f"Finished Runing 40nodes Data Flow")
          except:
            await exception_handling(f"Failed to run 40nodes Data Flow", user)
            raise

        async with event(self, "04: Signing Out"):
          try:  
            self.logger.info(f"Start: Signing Out from SAS Studio")
            await page.locator(".sas_components-Banner-Banner_avatar-container").click()
            await page.get_by_text("Sign out").click()
            await expect(page.get_by_role("heading", name="You have signed out.")).to_be_visible(timeout=60000)
            self.logger.info(f"Successfully Signed Out")
          except:
            await exception_handling(f"Failed to Sign Out", user)
            raise

 
