import unittest
from unittest.mock import Mock, patch

import app as launcher


class LauncherTests(unittest.TestCase):
    def test_failed_server_preserves_exit_code_without_opening_browser(self):
        process = Mock(returncode=1)
        process.poll.return_value = 1
        with patch.object(launcher.subprocess, "Popen", return_value=process), patch.object(launcher.time, "sleep"), patch.object(launcher.webbrowser, "open") as browser, patch("builtins.print"):
            self.assertEqual(launcher.main(), 1)
            browser.assert_not_called()
            process.wait.assert_called_once_with(timeout=5)

    def test_interrupt_during_startup_stops_the_server(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(launcher.subprocess, "Popen", return_value=process), patch.object(launcher.time, "sleep", side_effect=KeyboardInterrupt), patch.object(launcher.os, "name", "posix"), patch("builtins.print"):
            self.assertEqual(launcher.main(), 0)
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=5)
