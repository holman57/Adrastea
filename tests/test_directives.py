import tempfile
import unittest
from pathlib import Path
from adrastea.directives import DirectiveWatcher


class TestDirectiveWatcher(unittest.TestCase):
    def test_file_directive_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dir_file = Path(tmpdir) / "DIRECTIVES.txt"
            watcher = DirectiveWatcher(directives_file=dir_file)

            # Initially empty
            self.assertIsNone(watcher.check_file_directive())

            # User adds a directive
            with open(dir_file, "a", encoding="utf-8") as f:
                f.write("\nRun full security scan\n")

            detected = watcher.check_file_directive()
            self.assertEqual(detected, "Run full security scan")

            # Subsequent check should return None (file was reset)
            self.assertIsNone(watcher.check_file_directive())


if __name__ == "__main__":
    unittest.main()
