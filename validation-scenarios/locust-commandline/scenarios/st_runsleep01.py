# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from events import *
from auth import *
from exception import *
from locust_plugins.users.playwright import PlaywrightUser, pw, event, PageWithRetry
import traceback
import asyncio
import logging
from locust import runners

class st_runsleep01(PlaywrightUser):

    logger = logging.getLogger(__name__)
    multiplier = 1
    TIMEOUT_SHORT = 20000
    TIMEOUT_LONG =  60000

    @task
    @pw
    async def test_st_runsleep01(self, page: PageWithRetry):

        browser = self.browser
        context = self.browser_context

        page.set_default_timeout(timeout=self.TIMEOUT_LONG)
        if len(usernames) == 0:
            self.logger.info(f"No more users in the list, exiting as success")
            exit(0)


        user_ray = usernames.pop(random.randrange(len(usernames)))
        user = user_ray[0]
        password = user_ray[1]

        async with event(self, "01: Starting New studioProg01 tests"):
          try:  
            self.logger.info(f"Authenticating to SASLogon")
            await ldap_auth(page, user, password)
            self.logger.info(f"Authentication Successful")
          except:
            await exception_handling("Failed to Authenticate", user)
            raise        

        async with event(self, "02: Navigating to SAS Studio"):
            self.logger.info(f"Navigating to SAS Studio")
            await page.goto("/SASStudio/" , timeout=60000)
            timestamp = random.randint(1000, 9999)
           
        async with event(self, "04: Creating SAS Studio compute Context"):
          try:  
            self.logger.info(f"Start: Creating Studio Compute Context")
            await expect(page.get_by_test_id("appHeaderToolbar-studioActiveServerObjectMarker").locator("svg")).not_to_be_visible(timeout=60000)
            await expect(page.get_by_test_id("appHeaderToolbar-studioActiveServerButton")).to_be_visible(timeout=60000) 
            time.sleep(3) 
            self.logger.info(f"Closing the Start Page Tab")
            await page.get_by_test_id("tab-0").get_by_text("Start Page").click()
            await page.locator(".sas-icon.sas_components-SVG-SVG_svg.sas_components-SVG-SVG_icon.sas_components-Icon-Icon_icon > .CloseTab").click()
            self.logger.info(f"Opening the New SAS Program Tab")
            await page.get_by_test_id("appHeaderToolbar-new-button").click()
            await page.get_by_test_id("appHeaderToolbar-sascode-text").click()   
            await page.get_by_test_id("tab-group-bar-_root_").get_by_text("SAS Program.sas").click()
            await page.locator(".view-line").first.click()
            self.logger.info(f"Waiting for runButton to be enabled")
            await expect(page.get_by_test_id("programViewPane-toolbar-runButton")).to_be_enabled(timeout=60000)
            self.logger.info(f"Finished Creating Studio Compute Context")
          except:
            await exception_handling("Failed to create compute context", user)
            raise


        async with event(self,"04: Run SAS Program"):
            self.logger.info(f"Start: Run SAS Program Block")
            self.logger.info(f"Opening sleep_20.sas program")
            await page.get_by_test_id("appHeaderToolbar-open").click()
            await page.get_by_role("button", name="SAS Folders SAS Content").dblclick()
            await page.get_by_test_id("explorer-dialog-folder-tree").get_by_text("SAS Content").dblclick()
            await page.get_by_test_id("member-list-grid-wrapper").get_by_text("Public").dblclick()
            await page.get_by_test_id("member-list-grid-wrapper").get_by_text("sleep_20.sas").click()
            await page.get_by_test_id("file-folder-dialog-firstButton").click()
            self.logger.info(f"Finished opening sleep_20.sas program")
            await page.get_by_test_id("tab-group-bar-_root_").get_by_text("sleep_20.sas").click()
            await page.get_by_test_id("tab-group-bar-left").get_by_text("Code").click()            
            await page.get_by_test_id("programViewPane-toolbar-runButton").click()     
            await expect(page.get_by_test_id("tab-group-bar-_root_").get_by_label("Processing").locator("svg")).not_to_be_visible(timeout=120000)
            await expect(page.get_by_test_id("programViewPane-toolbar-runButton")).to_be_enabled(timeout=120000)
            await expect(page.get_by_test_id("tab-group-bar-right").get_by_text("Results")).to_be_visible(timeout=60000)
            time.sleep(2)
            self.logger.info(f"Finished Running SAS Program")

        async with event(self, "05: Signing Out"):
          try:  
            self.logger.info(f"Start: Signing Out from SAS Studio")
            await page.locator(".sas_components-Banner-Banner_avatar-container").click()
            await page.get_by_text("Sign out").click()
            try:
               await page.get_by_role("button", name="Discard and exit").click(timeout=6000)
            except PlaywrightTimeoutError:
               print("Discard and Exit dialog.") 
               pass           
            await expect(page.get_by_role("heading", name="You have signed out.")).to_be_visible(timeout=60000)
            self.logger.info(f"Successfully Signed Out")
          except:
            await exception_handling(f"Failed to Sign Out", user)
            raise




