"""Check repeatable exports and protection of personal edits."""
import tempfile
import unittest
from pathlib import Path

from tools.export_obsidian import export


class ExportTests(unittest.TestCase):
    def test_graph_refresh_preserves_personal_notes_and_rejects_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            personal = vault / 'Personal.md'
            personal.write_text('Do not change this note.')
            export(vault)
            folder = vault / 'AI Studio'
            self.assertEqual(len(list(folder.rglob('*.md'))), 41)
            export(vault)
            self.assertEqual(personal.read_text(), 'Do not change this note.')
            guide = folder / 'Guides' / 'AI Studio - Workspace Authoring.md'
            guide.write_text(guide.read_text()+'\nMy own edits.\n')
            with self.assertRaisesRegex(RuntimeError,'Local notes would be overwritten'):
                export(vault)
            self.assertTrue(guide.read_text().endswith('My own edits.\n'))


if __name__ == '__main__':
    unittest.main()
