# SAS Validation Scenarios

## Overview
The **sas-validation-scenarios** repository contains a collection of tools and scripts designed to run automated tests against various SAS Viya 4 applications to verify functionality and performance.
These tests are fully self-contained and can be executed on any cloud platform and across any SAS Viya cadence.
They can be run as single-user tests or scaled to simulate load with multiple concurrent users.
The only requirement is access to a valid SAS Viya 4 web application.
Before getting started, review the following documents:

- [What are validation scenarios?](./documentation/INTRODUCTION.md)
- [Where and how to execute sas-valdiation-scenarios](documentation/BEFORE-YOU-START.md)

## Getting Started
As new versions of SAS Viya are released, architectural updates, web UI changes, and feature additions or deprecations may occur.
Such changes can affect the behavior and compatibility of validation scenarios.
When a new cadence becomes available, the sas-validation-scenarios framework is validated against that release.

To manage these differences, each branch of this repository is aligned to the Viya cadence it supports.
Updates or adjustments are implemented and maintained within the associated branch to ensure compatibility and consistent test coverage across Viya versions.
**Whenever you are using the sas-validation-scenarios project, you must ensure you are using the branch with the label that corresponds to your specific Viya deployment.**

See [VERSIONS.md](VERSIONS.md) for a list of currently supported versions.

> [!NOTE]
> The project's main branch is currently targeting 2026.05 Viya 4 deployments.

## Scenarios and Resources

The sas-validation-scenariso are built up of Scenarios and Resources.
In simplest terms, Scenarios can be defined as a usecase or a testcase that accomplishes a certain flow.
Resources are the Viya content required to run these scenarios.
Resource setup is a ery important step to be performed before you run the scenarios.
If resources are not set up correctly in your Viya environment, your scenarios will not execute correctly and will fail.
For a detailed description refer to: 

- [What are scenarios?](./documentation/SCENARIOS-GUIDE.md)
- [List of Available Scenarios](./documentation/SCENARIOS-GUIDE.md)
- [Resource setup for specific scenarios](./documentation/RESOURCES-SETUP.md)

## Executing Validation Scenarios
Once you have decided [where and how to execute sas-valdiation-scenarios](documentation/BEFORE-YOU-START.md) refer to the following docs to get started: 
- [Getting Started with Running Locust Locally Outside of Kubernetes Using Locust Commands](./documentation/GETTING-STARTED-WITH-RUNNING-LOCUST-LOCALLY.md)
- [Getting Started with Running Locust on Kubernetes](./documentation/GETTING-STARTED-WITH-LOCUST-ON-KUBERNETES.md)

## Results Analysis
When running validation scenarios under load, performing a scaling analysis is essential to identify potential bottlenecks, problems, and performance issues.
Comparing response times across different user loads (e.g., 5, 10, 15, 20, 50, 100 users) provides valuable insight into how well the system handles increasing demand and whether it efficiently utilizes additional resources.
Refer to the [ResultsAnalysis.md](./documentation/ResultsAnalysis.md) section for step-by-step instructions on how to use execution results and generated CSV files to perform scaling analysis and apply analytics using SAS Visual Analytics.

## Troubleshooting
See [TROUBLESHOOTING.md](./documentation/TROUBLESHOOTING.md)
This document has a compilation of the various issues and their solutions we have encountered while running the sas-validation-scenarios.

## License
This project is licensed under the [Apache 2.0 License](LICENSE).

## Contributing
Maintainers are accepting patches and contributions to this project.
Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details about submitting contributions to this project.

## Third-Party Dependencies
This framework leverages several open source tools to automate, scale, and validate SAS Viya deployments.

| Dependency | License |
| ---------- | ------- |
| [Locust](https://locust.io/) | [MIT](https://github.com/locustio/locust/blob/master/LICENSE) |
| [Playwright](https://playwright.dev/python/) | [Apache License 2.0](https://github.com/microsoft/playwright/blob/main/LICENSE) |
| [Locust Plugins](https://github.com/SvenskaSpel/locust-plugins) | [Apache License 2.0](https://github.com/SvenskaSpel/locust-plugins/blob/master/LICENSE) |

Locust is an open source performance testing framework used to generate scalable, automated, and distributed load tests.
It integrates seamlessly with Playwright to enable UI-driven performance testing.
Playwright is powerful end-to-end testing framework for Python that automates browser interactions to validate user interfaces and application workflows.
Locust Plugins is community-developed project that extends Locust's capabilities, providing integration with Playwright and other utilities to enhance performance testing for SAS Viya environments.
