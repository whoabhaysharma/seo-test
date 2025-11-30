import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from seo_auditor.ui import run_image_alt_fetch, run_image_alt_update

class TestImageAltUpdate(unittest.TestCase):

    @patch('seo_auditor.ui.fetch_page_images')
    def test_run_image_alt_fetch(self, mock_fetch):
        # Mock return value of fetch_page_images
        mock_fetch.return_value = [
            {'url': 'http://example.com/img1.jpg', 'current_alt': 'alt1', 'attachment_id': 123},
            {'url': 'http://example.com/img2.jpg', 'current_alt': 'alt2', 'attachment_id': None}
        ]

        progress_mock = MagicMock()
        data, message = run_image_alt_fetch('http://example.com', "user", "pass", progress=progress_mock)

        self.assertEqual(len(data), 2)
        # Check first row
        self.assertEqual(data[0][0], "![Preview](http://example.com/img1.jpg)")
        self.assertEqual(data[0][1], "http://example.com/img1.jpg")
        self.assertEqual(data[0][2], "alt1")
        self.assertEqual(data[0][3], "alt1")
        self.assertEqual(data[0][4], "123")

        # Check second row (no ID)
        self.assertEqual(data[1][4], "N/A")

    @patch('seo_auditor.ui.update_image_alts')
    def test_run_image_alt_update_pandas(self, mock_update):
        # Prepare a DataFrame as it would come from Gradio
        data = {
            "Preview": ["![Preview](...)", "![Preview](...)"],
            "Image URL": ["url1", "url2"],
            "Current Alt": ["curr1", "curr2"],
            "New Alt Text": ["new1", "new2"],
            "Attachment ID": ["101", "102"]
        }
        df = pd.DataFrame(data)

        mock_update.return_value = (True, "Updated")
        progress_mock = MagicMock()

        result = run_image_alt_update("http://page.url", df, "user", "pass", progress=progress_mock)

        self.assertIn("Update Complete", result)

        # Verify call to update_image_alts
        args, _ = mock_update.call_args
        updates = args[3]
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[0]['attachment_id'], 101)
        self.assertEqual(updates[0]['new_alt'], 'new1')
        self.assertEqual(updates[1]['attachment_id'], 102)
        self.assertEqual(updates[1]['new_alt'], 'new2')

    @patch('seo_auditor.ui.update_image_alts')
    def test_run_image_alt_update_list(self, mock_update):
        # Prepare list of lists (fallback case)
        data = [
            ["prev", "url1", "curr1", "new1", "101"],
            ["prev", "url2", "curr2", "new2", "102"]
        ]

        mock_update.return_value = (True, "Updated")
        progress_mock = MagicMock()

        result = run_image_alt_update("http://page.url", data, "user", "pass", progress=progress_mock)

        self.assertIn("Update Complete", result)

        # Verify call to update_image_alts
        args, _ = mock_update.call_args
        updates = args[3]
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[0]['attachment_id'], 101)
        self.assertEqual(updates[0]['new_alt'], 'new1')

if __name__ == '__main__':
    unittest.main()
