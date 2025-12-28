import unittest
from unittest.mock import patch, MagicMock
import asyncio
import os
from seo_auditor.ui import run_capture_ui

class TestUICapture(unittest.TestCase):
    @patch('seo_auditor.ui.asyncio.run')
    @patch('seo_auditor.ui.create_pdf')
    def test_run_capture_ui_success(self, mock_create_pdf, mock_asyncio_run):
        # Setup mocks
        mock_asyncio_run.return_value = ("/tmp/folder", ["/tmp/folder/1.png"])
        mock_create_pdf.return_value = "/tmp/screenshots.pdf"

        # Test input
        urls_input = "https://example.com"

        # Call function
        screenshot_paths, pdf_path, status = run_capture_ui(urls_input)

        # Verify calls
        mock_asyncio_run.assert_called_once()
        mock_create_pdf.assert_called_once()

        # Verify arguments passed to create_pdf
        # It should receive the screenshot paths list
        self.assertEqual(mock_create_pdf.call_args[0][0], ["/tmp/folder/1.png"])
        # And a filename ending in .pdf
        self.assertTrue(mock_create_pdf.call_args[0][1].endswith('.pdf'))

        # Verify return values
        self.assertEqual(screenshot_paths, ["/tmp/folder/1.png"])
        self.assertEqual(pdf_path, "/tmp/screenshots.pdf")
        self.assertIn("converted to PDF", status)

    @patch('seo_auditor.ui.asyncio.run')
    def test_run_capture_ui_failure(self, mock_asyncio_run):
        # Setup mocks to return failure (empty list of paths)
        mock_asyncio_run.return_value = ("/tmp/folder", [])

        # Test input
        urls_input = "https://example.com"

        # Call function
        screenshot_paths, pdf_path, status = run_capture_ui(urls_input)

        # Verify return values for failure case
        self.assertIsNone(screenshot_paths)
        self.assertIsNone(pdf_path)
        self.assertIn("Failed to capture screenshots", status)

if __name__ == '__main__':
    unittest.main()
