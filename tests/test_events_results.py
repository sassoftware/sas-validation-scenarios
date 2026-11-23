"""Unit tests for the result publisher in framework/execution/common/events.py.

events.py imports Locust, Playwright and the Kubernetes user loader at import time, so those
modules are stubbed; the publisher itself only needs the StatsCSV rendering interface.
"""

import base64
import contextlib
import gzip
import importlib.util
import io
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

EVENTS_PATH = Path(__file__).parent.parent / "framework" / "execution" / "common" / "events.py"


class _Hook:
    def __init__(self):
        self.listeners = []

    def add_listener(self, fn):
        self.listeners.append(fn)
        return fn


class _MasterRunner:
    pass


class _WorkerRunner:
    pass


class _FakeStatsCSV:
    def __init__(self, environment, percentiles):
        self.environment = environment

    def requests_csv(self, writer):
        writer.writerow(["Type", "Name", "Request Count", "Failure Count"])
        writer.writerow(["GET", "/x", 5, 0])

    def failures_csv(self, writer):
        writer.writerow(["Method", "Name", "Error", "Occurrences"])

    def exceptions_csv(self, writer):
        writer.writerow(["Count", "Message", "Traceback", "Nodes"])
        writer.writerow([1, "boom", "Traceback (most recent call last):\n  line 1\nValueError: boom", "w1"])


def _stub_modules():
    events = types.SimpleNamespace(init=_Hook(), test_start=_Hook(), quitting=_Hook(), quit=_Hook())
    any_attr = lambda name: types.SimpleNamespace(**{a: object() for a in name.split()})  # noqa: E731
    modules = {
        "playwright": types.ModuleType("playwright"),
        "playwright._impl": types.ModuleType("playwright._impl"),
        "playwright._impl._errors": any_attr("TargetClosedError"),
        "playwright.async_api": any_attr("Page expect async_playwright TimeoutError"),
        "locust": types.SimpleNamespace(
            task=lambda f: f, events=events, HttpUser=object, TaskSet=object,
            between=lambda *a: None, run_single_user=lambda *a: None,
        ),
        "locust.runners": types.SimpleNamespace(MasterRunner=_MasterRunner, WorkerRunner=_WorkerRunner),
        "locust.exception": any_attr("StopUser"),
        "locust.stats": types.SimpleNamespace(StatsCSV=_FakeStatsCSV, PERCENTILES_TO_REPORT=[0.5]),
        "locust_plugins": types.ModuleType("locust_plugins"),
        "locust_plugins.users": types.ModuleType("locust_plugins.users"),
        "locust_plugins.users.playwright": types.SimpleNamespace(
            PageWithRetry=object, PlaywrightUser=type("PlaywrightUser", (), {}),
            PlaywrightScriptUser=object, pw=lambda f: f, event=lambda *a, **k: None,
        ),
        "locust_plugins.csvreader": any_attr("CSVReader"),
        "dotenv": types.SimpleNamespace(load_dotenv=lambda *a, **k: None, dotenv_values=lambda *a, **k: {}),
        "scenario_utils": types.SimpleNamespace(
            UsersManager=lambda: types.SimpleNamespace(get_user_list=lambda: [])
        ),
    }
    return modules


def _load_events():
    spec = importlib.util.spec_from_file_location("events_under_test", EVENTS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decode(payload):
    return gzip.decompress(base64.b64decode(payload)).decode("utf-8")


class EventsResultPublisherTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(sys.modules, _stub_modules())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.events = _load_events()

    def _publish(self, runner, exit_code=0):
        self.events._environment = types.SimpleNamespace(runner=runner)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.events.publish_results(exit_code=exit_code)
        return out.getvalue()

    def test_quit_listener_is_registered(self):
        locust_events = sys.modules["locust"].events
        self.assertIn(self.events.publish_results, locust_events.quit.listeners)

    def test_master_publishes_single_line_results_that_round_trip(self):
        output = self._publish(_MasterRunner(), exit_code=1)
        lines = output.splitlines()
        self.assertEqual([line.split(" ")[1] for line in lines], ["stats", "failures", "exceptions", "exit_code"])
        for line in lines:
            self.assertTrue(line.startswith("SAS_VALIDATION_RESULT "))
            self.assertEqual(len(line.split(" ")), 3)
        values = {line.split(" ")[1]: line.split(" ")[2] for line in lines}
        self.assertEqual(values["exit_code"], "1")
        self.assertEqual(_decode(values["stats"]), "Type,Name,Request Count,Failure Count\r\nGET,/x,5,0\r\n")
        self.assertEqual(_decode(values["failures"]), "Method,Name,Error,Occurrences\r\n")
        self.assertIn("ValueError: boom", _decode(values["exceptions"]))
        self.assertNotIn("Traceback", output)

    def test_workers_do_not_publish(self):
        self.assertEqual(self._publish(_WorkerRunner()), "")

    def test_rendering_failure_does_not_raise(self):
        self.events._environment = types.SimpleNamespace(runner=_MasterRunner())
        broken = types.SimpleNamespace(StatsCSV=mock.Mock(side_effect=RuntimeError("x")), PERCENTILES_TO_REPORT=[])
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"locust.stats": broken}), contextlib.redirect_stdout(out):
            self.events.publish_results(exit_code=0)
        self.assertEqual(out.getvalue().strip(), "SAS_VALIDATION_RESULT publish_failed RuntimeError")


if __name__ == "__main__":
    unittest.main()
