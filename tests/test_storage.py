import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import storage


class TestStorage(unittest.TestCase):

    def setUp(self):
        # 为每个测试创建独立的临时目录
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_draft_dir = Path(self.temp_dir.name)

        # 将存储目录替换为临时目录
        self.patcher = patch.object(
            storage, "DRAFT_DIR", self.test_draft_dir
        )
        self.patcher.start()

        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def test_save_draft_success(self):
        """测试正常保存草稿"""

        result = storage.save_draft("M001", "19:00")

        self.assertTrue(result["success"])
        self.assertTrue(result["created"])
        self.assertFalse(result["duplicate"])

        # 检查文件是否真正创建
        self.assertTrue(
            (self.test_draft_dir / "M001_1900.json").exists()
        )

    def test_duplicate_save(self):
        """测试重复保存不会创建重复文件"""

        first_result = storage.save_draft("M001", "19:00")
        second_result = storage.save_draft("M001", "19:00")

        self.assertTrue(first_result["success"])
        self.assertTrue(second_result["success"])

        self.assertFalse(second_result["created"])
        self.assertTrue(second_result["duplicate"])

        # 相同素材和时间只能有一个文件
        files = list(self.test_draft_dir.glob("*.json"))
        self.assertEqual(len(files), 1)

    def test_get_draft(self):
        """测试读取已经保存的草稿"""

        storage.save_draft("M001", "19:00")

        result = storage.get_draft("M001", "19:00")

        self.assertTrue(result["success"])
        self.assertEqual(
            result["draft"]["material_id"], "M001"
        )
        self.assertEqual(
            result["draft"]["publish_time"], "19:00"
        )

    def test_list_drafts(self):
        """测试列出所有草稿"""

        storage.save_draft("M001", "19:00")
        storage.save_draft("M002", "20:00")

        result = storage.list_drafts()

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["drafts"]), 2)

    def test_save_failure(self):
        """测试模拟磁盘写入失败"""

        with patch.object(
            Path, "open", side_effect=OSError("模拟磁盘写入失败")
        ):
            result = storage.save_draft("M001", "19:00")

        self.assertFalse(result["success"])
        self.assertFalse(result["created"])
        self.assertIn("草稿保存失败", result["message"])

    def test_invalid_publish_time(self):
        """测试非法发布时间"""

        result = storage.save_draft("M001", "25:00")

        self.assertFalse(result["success"])
        self.assertIn("草稿保存失败", result["message"])


if __name__ == "__main__":
    unittest.main()