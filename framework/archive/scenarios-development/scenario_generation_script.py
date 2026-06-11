# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import re
import os
import argparse
import yaml

def convert_test_to_framework_version(input_code):
    lines = input_code.splitlines()
    output = []
    in_dev_test = False
    in_framework_test = False
    in_param_block = False
    in_event_block = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip any line with more than 10 '#' characters
        if line.count('#') > 10:
            i += 1
            continue

        # Skip DEV_TEST blocks
        if stripped.startswith("###!DEV_TEST"):
            in_dev_test = True
            i += 1
            continue
        if stripped.startswith("###$!DEV_TEST"):
            in_dev_test = False
            i += 1
            continue
        if in_dev_test:
            i += 1
            continue

        # Handle FRAMEWORK_TEST block
        if stripped.startswith("###!FRAMEWORK_TEST"):
            in_framework_test = True
            i += 1
            continue
        if stripped.startswith("###$!FRAMEWORK_TEST"):
            in_framework_test = False
            i += 1
            continue
        if in_framework_test:
            hash_index = line.find("#")
            if hash_index != -1:
                uncommented_line = line[:hash_index] + line[hash_index + 1:]
                if uncommented_line[hash_index] == " ":
                    uncommented_line = (
                        uncommented_line[:hash_index] + uncommented_line[hash_index + 1:]
                    )
                output.append(uncommented_line.rstrip())
            else:
                output.append(line.rstrip())
            i += 1
            continue

        # Handle parameters block
        if stripped.startswith("###!DEV_CONVERT_PARAMETERS"):
            in_param_block = True
            i += 1
            continue
        if stripped.startswith("###$!DEV_CONVERT_PARAMETERS"):
            in_param_block = False
            i += 1
            continue
        if in_param_block:
            line_no_self = line.replace("self.", "")
            if line_no_self.startswith("    "):
                line_no_self = line_no_self[4:]
            output.append(line_no_self)
            i += 1
            continue

        # Handle events block
        if stripped.startswith("###!DEV_CONVERT_EVENTS"):
            in_event_block = True
            i += 1
            continue
        if stripped.startswith("###$!DEV_CONVERT_EVENTS"):
            in_event_block = False
            i += 1
            continue
        if in_event_block:
            line = line.replace('f"{self.BASE_URL}', '"')
            method_def = re.match(r'^(\s*)async def \w+\(.*\):', line)
            if method_def:
                indent = method_def.group(1)
                j = i + 1
                event_text = "Unknown event"
                while j < len(lines):
                    logger_line = lines[j].strip()
                    logger_match = re.search(r'self\.logger\.info\("(.+?)"\)', logger_line)
                    if logger_match:
                        event_text = logger_match.group(1)
                        break
                    elif logger_line == "":
                        j += 1
                        continue
                    else:
                        break
                output.append(f'{indent}    async with event(self, "{event_text}"):')
                i += 1
                continue
            else:
                output.append("    " + line)
                i += 1
                continue

        # Default output
        output.append(line)
        i += 1

    return "\n".join(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert all test files in a directory to framework version.")
    parser.add_argument("scenario_dir", help="Path to the directory containing test files.")
    args = parser.parse_args()

    scenario_dir = os.path.abspath(args.scenario_dir)
    scenario_name = os.path.basename(os.path.normpath(scenario_dir))

    output_dir = os.path.join("..", "scenarios", scenario_name, "tests")
    output_dir_debug = os.path.join("..", "scenarios", scenario_name)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(output_dir_debug, exist_ok=True)

    test_files = [f for f in os.listdir(scenario_dir) if f.endswith(".py")]
    test_names = []
    for test_file in test_files:
        test_name = os.path.splitext(test_file)[0]
        test_names.append(test_name)

        input_file = os.path.join(scenario_dir, test_file)

        # Framework version
        with open(input_file, encoding="utf-8") as f:
            code = f.read()
        converted = convert_test_to_framework_version(code)

        output_file = os.path.join(output_dir, f"{test_name}.py")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(converted)

        # Conversion to headless version
        modified_code = code.replace("headless=False", "headless=True")
        output_file_debug = os.path.join(output_dir_debug, f"debug_{test_name}.py")
        with open(output_file_debug, "w", encoding="utf-8") as f:
            f.write(modified_code)

    # Create workload definition
    wrkld_dir = os.path.join("..", "workload-definitions")
    os.makedirs(wrkld_dir, exist_ok=True)

    output_wrkld_file = os.path.join(wrkld_dir, f"{scenario_name}-wrkld-def.yaml")

    if test_names:
        workload_spec = {
            "workload-definitions": {
                "workload-definition-specs": [
                    {
                        "name": scenario_name,
                        "description": scenario_name,
                        "custom-resource-spec": {
                            "namespace": "testing",
                            "config-map-name": f"{scenario_name}-map",
                            "k8s-operator": "locust-k8s-operator.yaml",
                            "workloads": [
                                {
                                    "name": test_name,
                                    "path": f"{scenario_name}/tests",
                                    "task": f"{test_name}.py",
                                    "csv": "stats.csv",
                                    "users": 1,
                                    "spawn-rate": 3,
                                    "iterations": 1,
                                    "worker-replicas": 1,
                                }
                                for test_name in test_names
                            ],
                            "custom-modules": [
                                {"name": "common", "path": "framework/execution/common", "task": "events.py"},
                                {"name": "common", "path": "framework/execution/common", "task": "auth.py"},
                                {"name": "common", "path": "framework/execution/common", "task": "exception.py"},
                            ],
                        },
                    }
                ]
            }
        }

        # Save workload definition
        with open(output_wrkld_file, "w", encoding="utf-8") as f:
            yaml.dump(workload_spec, f, sort_keys=False)

        print(f"All test files in {scenario_dir} were converted to locust version and saved to:\n- ../scenarios/{scenario_name}/tests")
        print(f"Workload definition was saved to: {output_wrkld_file}")

    else:
        print(f"No test files found in {scenario_dir}, skipping workload generation.")
