
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from src import tools, storage


class TestTools(unittest.TestCase):

    def setUp(self):
        """
        Create an isolated environment for each test.
        """
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_draft_dir = Path(self.temp_dir.name)

        # Redirect draft storage to a temporary directory
        self.draft_dir_patcher = patch.object(
            storage,
            "DRAFT_DIR",
            self.test_draft_dir
        )
        self.draft_dir_patcher.start()

        # Keep a copy of the original material data
        self.original_materials = tools.MATERIALS.copy()

    def tearDown(self):
        """
        Restore the original environment.
        """
        tools.MATERIALS.clear()
        tools.MATERIALS.update(self.original_materials)

        self.draft_dir_patcher.stop()
        self.temp_dir.cleanup()

    # -----------------------------
    # 1. read_material tests
    # -----------------------------

    def test_read_material_success(self):
        """Test reading an existing material."""
        result = tools.read_material("M01")

        self.assertTrue(result["success"])
        self.assertFalse(result["missing"])
        self.assertEqual(result["material_id"], "M01")

    def test_read_material_not_found(self):
        """Test reading a non-existent material."""
        result = tools.read_material("M999")

        self.assertFalse(result["success"])
        self.assertTrue(result["missing"])
        self.assertIsNone(result["material"])

    def test_read_material_incomplete(self):
        """Test reading a material with missing metadata."""
        result = tools.read_material("M003")

        self.assertTrue(result["success"])
        self.assertTrue(result["missing"])
        self.assertIn("metadata", result["missing_fields"])

    # -----------------------------
    # 2. check_rules tests
    # -----------------------------

    def test_check_rules_low_risk(self):
        """Test that low-risk material passes review."""
        result = tools.check_rules("M01")

        self.assertTrue(result["success"])
        self.assertEqual(result["review_status"], "passed")
        self.assertEqual(result["risk_level"], "low")
        self.assertTrue(result["can_schedule"])

    def test_check_rules_medium_risk(self):
        """Test that medium-risk material requires manual review."""
        tools.MATERIALS["TEST_MEDIUM"] = {
            "name": "Medium Risk Material",
            "status": "ready",
            "metadata": {
                "title": "Test",
                "description": "Medium risk test"
            },
            "risk_level": "medium",
            "risk_reasons": ["Manual review required"]
        }

        result = tools.check_rules("TEST_MEDIUM")

        self.assertEqual(result["review_status"], "needs_review")
        self.assertFalse(result["can_schedule"])

    def test_check_rules_high_risk(self):
        """Test that high-risk material is blocked."""
        result = tools.check_rules("M002")

        self.assertTrue(result["success"])
        self.assertEqual(result["review_status"], "blocked")
        self.assertEqual(result["risk_level"], "high")
        self.assertFalse(result["can_schedule"])

    def test_check_rules_unknown_risk(self):
        """Test that an unknown risk level is blocked."""
        tools.MATERIALS["TEST_UNKNOWN"] = {
            "name": "Unknown Risk Material",
            "status": "ready",
            "metadata": {
                "title": "Test",
                "description": "Unknown risk test"
            },
            "risk_level": "critical",
            "risk_reasons": []
        }

        result = tools.check_rules("TEST_UNKNOWN")

        self.assertEqual(result["review_status"], "blocked")
        self.assertEqual(result["risk_level"], "unknown")
        self.assertFalse(result["can_schedule"])

    def test_check_rules_missing_risk_level(self):
        """Test that a missing risk level is blocked."""
        tools.MATERIALS["TEST_MISSING_RISK"] = {
            "name": "Missing Risk Material",
            "status": "ready",
            "metadata": {
                "title": "Test",
                "description": "Missing risk level"
            }
        }

        result = tools.check_rules("TEST_MISSING_RISK")

        self.assertEqual(result["review_status"], "blocked")
        self.assertEqual(result["risk_level"], "unknown")
        self.assertFalse(result["can_schedule"])

    # -----------------------------
    # 3. query_slots tests
    # -----------------------------

    def test_query_slots(self):
        """Test querying available publishing slots."""
        result = tools.query_slots()

        self.assertTrue(result["success"])
        self.assertIn("18:00", result["occupied"])
        self.assertNotIn("18:00", result["available"])

        self.assertIn("19:00", result["available"])
        self.assertIn("20:00", result["available"])
        self.assertIn("21:00", result["available"])

    def test_query_slots_with_existing_draft(self):
        """Test that an existing draft occupies its time slot."""
        save_result = tools.save_schedule_draft(
            "M01",
            "19:00"
        )

        self.assertTrue(save_result["success"])

        result = tools.query_slots()

        self.assertNotIn("19:00", result["available"])
        self.assertIn("19:00", result["occupied"])

    # -----------------------------
    # 4. save_schedule_draft tests
    # -----------------------------

    def test_save_schedule_draft_success(self):
        """Test successfully saving a scheduling draft."""
        result = tools.save_schedule_draft(
            "M01",
            "19:00"
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["created"])
        self.assertFalse(result["duplicate"])

        self.assertEqual(
            result["draft"]["material_id"],
            "M01"
        )

        self.assertEqual(
            result["draft"]["publish_time"],
            "19:00"
        )

    def test_save_schedule_draft_missing_material(self):
        """Test that a missing material cannot be scheduled."""
        result = tools.save_schedule_draft(
            "M999",
            "19:00"
        )

        self.assertFalse(result["success"])

    def test_save_schedule_draft_high_risk(self):
        """Test that a high-risk material cannot be scheduled."""
        result = tools.save_schedule_draft(
            "M002",
            "19:00"
        )

        self.assertFalse(result["success"])
        self.assertIn("review", result)

    def test_save_schedule_draft_invalid_time(self):
        """Test that an unsupported time cannot be saved."""
        result = tools.save_schedule_draft(
            "M01",
            "22:00"
        )

        self.assertFalse(result["success"])

    def test_save_schedule_draft_occupied_time(self):
        """Test that an occupied time cannot be saved."""
        result = tools.save_schedule_draft(
            "M01",
            "18:00"
        )

        self.assertFalse(result["success"])

    def test_save_schedule_draft_duplicate(self):
        """Test that duplicate requests do not create duplicate files."""
        first_result = tools.save_schedule_draft(
            "M01",
            "19:00"
        )

        second_result = tools.save_schedule_draft(
            "M01",
            "19:00"
        )

        self.assertTrue(first_result["success"])
        self.assertTrue(second_result["success"])
        self.assertTrue(second_result["duplicate"])

        files = list(self.test_draft_dir.glob("*.json"))

        self.assertEqual(len(files), 1)

    def test_save_schedule_draft_same_time_different_material(self):
        """Test that another material cannot use an occupied time."""
        first_result = tools.save_schedule_draft(
            "M01",
            "19:00"
        )

        second_result = tools.save_schedule_draft(
            "M004",
            "19:00"
        )

        self.assertTrue(first_result["success"])
        self.assertFalse(second_result["success"])

    def test_save_schedule_draft_failure(self):
        """Test that a storage failure is returned correctly."""
        with patch.object(
            tools,
            "persist_draft",
            return_value={
                "success": False,
                "created": False,
                "message": "模拟磁盘写入失败"
            }
        ):
            result = tools.save_schedule_draft(
                "M01",
                "19:00"
            )

        self.assertFalse(result["success"])
        self.assertIn("模拟磁盘写入失败", result["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
