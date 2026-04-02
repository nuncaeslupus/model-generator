import unittest

from model_generator import utils


class TestGeneratorUtils(unittest.TestCase):
    def test_deep_merge_simple(self):
        """Test simple dictionary merging."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = utils.deep_merge(base, override)
        expected = {"a": 1, "b": 3, "c": 4}
        self.assertEqual(result, expected)

    def test_deep_merge_nested(self):
        """Test recursive dictionary merging."""
        base = {"nested": {"x": 1, "y": 2}, "other": 5, "deep": {"a": {"b": 1}}}
        override = {"nested": {"y": 3, "z": 4}, "deep": {"a": {"c": 2}}}
        result = utils.deep_merge(base, override)
        expected = {
            "nested": {"x": 1, "y": 3, "z": 4},
            "other": 5,
            "deep": {"a": {"b": 1, "c": 2}},
        }
        self.assertEqual(result, expected)

    def test_path_to_import(self):
        """Test file path to python import string conversion."""
        # Standard path
        self.assertEqual(
            utils.path_to_import("backend/src/database/models"),
            "backend.src.database.models",
        )
        # With module name appended
        self.assertEqual(
            utils.path_to_import("backend/src/api", "routes"),
            "backend.src.api.routes",
        )
        # Root level
        self.assertEqual(utils.path_to_import("models"), "models")


if __name__ == "__main__":
    unittest.main()
