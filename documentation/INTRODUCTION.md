# What are SAS-Validation-Scenarios?
The **sas-validation-scenarios** repository contains a collection of tools and scripts designed to run automated tests against various **SAS Viya 4** applications to verify functionality and performance. These tests are fully self-contained and can be executed on any cloud platform and across any SAS Viya cadence. They can be run as single-user tests or scaled to simulate load with multiple concurrent users. The only requirement is access to a valid SAS Viya 4 web application.

> [!WARNING]
The tests in SAS Validation Scenarios are designed to verify functionality and performance of various SAS Viya 4 applications by simulating various common uses cases. They are not intended to be comprehensive, nor do they guarantee compliance with any industry-specific regulatory requirements.

This framework is powered by [LOCUST](https://locust.io/), an open source performance load testing tool. It supports multiple test types, including UI-driven tests using Playwright for Python, command-line tests using the **SAS Viya CLI**, or other custom Python-based scenarios. Locust serves as the load generation engine and requires a Python test file as input. The repository provides a collection of pre-written and validated test scenarios for different Viya cadences, which can be executed directly against your environment.
