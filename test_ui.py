import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QLabel
from main import Monitor, STYLE

class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)
        cls.app.setQuitOnLastWindowClosed(False)

    def test_demo_render_expand_stale_and_exit_without_real_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = Monitor(root, demo=True)
            window.show()
            self.app.processEvents()
            self.assertIn("37%", window.summaries["codex"].text())
            self.assertIn("58%", window.summaries["claude"].text())
            window.pin_action.setChecked(True)
            self.app.processEvents()
            self.assertTrue(window.detail_scroll.isVisible())
            detail_text = " ".join(label.text() for label in window.detail.findChildren(QLabel))
            self.assertIn("每周", detail_text)
            window.states["codex"]["status"] = "连接失败"
            window.render()
            self.app.processEvents()
            self.assertIn("旧值", window.summaries["codex"].text())
            self.assertFalse((root / "usage.json").exists())
            self.assertFalse((root / "profiles").exists())
            window.quit_app()
            window.deleteLater()
            self.app.processEvents()

if __name__ == "__main__":
    unittest.main()
