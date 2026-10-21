import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from plot_jmh import load_groups, report_paths, task_throughput


class MergeReportsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.record = {
            "benchmark": "org.example.TasksBenchmark.vtPerWorker",
            "mode": "thrpt",
            "threads": 1,
            "params": {"parallelism": "16", "tasksPerSlot": "256", "handoff": "JOX"},
            "primaryMetric": {"score": 100, "scoreError": 10, "scoreUnit": "ops/s"},
        }

    def write(self, name, records):
        path = self.root / name
        path.write_text(json.dumps(records))
        return path

    def load(self, reports):
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            groups = load_groups(reports)
        return groups, log.getvalue()

    def test_directory_merges_new_parallelism_and_logs_sources(self):
        self.write("results.json", [self.record])
        additional = copy.deepcopy(self.record)
        additional["params"]["parallelism"] = "64"
        self.write("parallelism-64.json", [additional])
        (self.root / "empty.json").write_text("")
        self.write("unrelated.json", [{"benchmark": "org.example.StartEndBenchmark.startEnd"}])
        groups, log = self.load(self.root)
        points = next(iter(groups.values()))["vtPerWorker"]
        self.assertEqual({point[1] for point in points}, {16, 64})
        self.assertIn("parallelism-64.json: 1 added", log)
        self.assertIn("results.json: 1 added", log)
        self.assertIn("empty.json: empty file", log)
        self.assertIn("1 unrelated results skipped", log)
        self.assertIn("2 unique results from 2 contributing report(s)", log)

    def test_combined_report_does_not_duplicate_existing_results(self):
        self.write("results.json", [self.record])
        self.write("combined.json", [self.record])
        groups, log = self.load(self.root)
        self.assertEqual(len(next(iter(groups.values()))["vtPerWorker"]), 1)
        self.assertIn("1 identical duplicates skipped", log)

    def test_conflicting_scores_report_both_sources(self):
        self.write("first.json", [self.record])
        changed = copy.deepcopy(self.record)
        changed["primaryMetric"]["score"] = 200
        self.write("second.json", [changed])
        with self.assertRaisesRegex(ValueError, r"Conflicting results.*first.json.*second.json"):
            self.load(self.root)

    def test_explicit_report_excludes_other_files(self):
        selected = self.write("selected.json", [self.record])
        (self.root / "invalid.json").write_text("invalid")
        groups, _ = self.load([selected])
        self.assertEqual(len(groups), 1)
        self.assertEqual(report_paths([selected, self.root / "." / "selected.json"]), [selected])

    def test_invalid_json_includes_filename(self):
        invalid = self.root / "invalid.json"
        invalid.write_text("invalid")
        with self.assertRaisesRegex(ValueError, "Invalid JSON in .*invalid.json"):
            self.load(invalid)

    def test_non_array_is_rejected(self):
        invalid = self.write("object.json", {})
        with self.assertRaisesRegex(ValueError, "Expected a JMH JSON array.*object.json"):
            self.load(invalid)

    def test_empty_directory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "No JSON reports found"):
            self.load(self.root)

    def test_batch_throughput_and_error_are_scaled_by_task_count(self):
        self.assertEqual(task_throughput(self.record["primaryMetric"], "thrpt", 16 * 256),
                         (409600, (40960, 40960)))


if __name__ == "__main__":
    unittest.main()
