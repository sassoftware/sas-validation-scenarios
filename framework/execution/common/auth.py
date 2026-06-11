# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from playwright.async_api import Page, BrowserContext, Route, expect
from locust_plugins.users.playwright import PlaywrightUser, pw, event, PageWithRetry
import traceback
import logging


# This module authenticates to /SASLogon and signs the user in
# Authentication methods supported currently are:
#    - ldap
#    - engage


async def ldap_auth(page: Page, user, password):
    await page.goto("/SASLogon/home")
    await page.get_by_label("User ID:").click()
    await page.get_by_label("User ID:").fill(user)
    await page.get_by_label("Password:").click()
    await page.get_by_label("Password:").fill(password)
    logging.info(f"Logging in as user: {user}")
    #logging.info(f"Password is as follows: {password}")
    await page.get_by_role("button", name="Sign in").click()
    await expect(page.get_by_text("You have signed in. For")).to_be_visible()
    await expect(page.get_by_role("heading", name="You have signed in.")).to_be_visible()
    await expect(page.get_by_text("For increased security, sign")).to_be_visible()

async def engage_auth(page: Page, user, password):
    await page.goto("/SASLogon")
    await page.get_by_label("Username/Email").click()
    await page.get_by_label("Username/Email").fill(user)
    logging.info(f"Logging in as user: {user}")
    logging.info(f"Password is as follows: {password}")
    await page.get_by_role("button", name="Next").click()
    await page.get_by_label("Password").click()
    await page.get_by_label("Password").fill(password)
    await page.get_by_role("button", name="Sign In").click()
    await expect(page.get_by_role("heading", name="You have signed in.")).to_be_visible()
    await expect(page.get_by_label("SAS logo")).to_be_visible()
    await expect(page.get_by_text("For increased security, sign")).to_be_visible()

