import json
import tempfile
import unittest
from pathlib import Path

from auction_engine.run_layout import RunLayout


class RunLayoutTests(unittest.TestCase):
    def test_creates_stable_artifact_tree_and_latest_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = RunLayout.create(directory, "Profit Run / 55447")
            self.assertTrue(layout.raw_dir.is_dir())
            self.assertTrue(layout.outputs_dir.is_dir())
            self.assertTrue(layout.reports_dir.is_dir())
            self.assertTrue(layout.logs_dir.is_dir())
            self.assertTrue(layout.state_dir.is_dir())
            self.assertTrue(layout.metadata_dir.is_dir())
            self.assertTrue(layout.shared_cache_dir.is_dir())
            self.assertRegex(
                layout.run_id,
                r"^run_[A-Z][a-z]{2}_\d{2}_[A-Z][a-z]{2}_\d{4}_\d{2}-\d{2}-\d{2}_-0600_[0-9a-f]{8}$",
            )
            self.assertEqual("profit-run-55447", layout.run_name)
            latest = json.loads((Path(directory) / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(layout.run_id, latest["run_id"])
            self.assertEqual("CST (UTC-06:00)", latest["timezone"])
            self.assertRegex(latest["run_timestamp_rfc2822"], r"^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} (?:AM|PM) -0600$")
            self.assertTrue(latest["updated_at"].endswith("-06:00"))

    def test_relative_artifacts_are_confined_to_named_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = RunLayout.create(directory, "test")
            output = layout.artifact("outputs", "../unsafe/opportunities.csv")
            self.assertEqual(layout.outputs_dir / "opportunities.csv", output)

    def test_manifest_updates_without_losing_existing_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = RunLayout.create(directory, "test")
            layout.write_manifest(status="starting", settings={"workers": 8})
            manifest = layout.write_manifest(status="completed", counts={"items": 10})
            self.assertEqual({"workers": 8}, manifest["settings"])
            self.assertEqual("completed", manifest["status"])
            self.assertEqual({"items": 10}, manifest["counts"])


if __name__ == "__main__":
    unittest.main()
