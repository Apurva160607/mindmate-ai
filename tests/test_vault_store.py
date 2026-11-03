"""Run from the project root:  python -m unittest discover -s tests"""
import base64
from unittest.mock import patch
import os
import tempfile
import unittest
from pathlib import Path

import vault_store as vault

KEY_A = base64.urlsafe_b64encode(b"A" * 32).decode()
KEY_B = base64.urlsafe_b64encode(b"B" * 32).decode()
SECRET = b"Patient: Test Person. Blood group O+. SYNTHETIC DATA."


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MINDMATE_VAULT_DIR"] = os.path.join(self.tmp.name, "files")
        os.environ["MINDMATE_VAULT_DB"] = os.path.join(self.tmp.name, "vault.db")
        os.environ["MINDMATE_VAULT_KEY"] = KEY_A
        self.alice, self.bob = "email:alice@example.com", "google:bob-1"

    def tearDown(self):
        for name in ("MINDMATE_VAULT_DIR", "MINDMATE_VAULT_DB", "MINDMATE_VAULT_KEY"):
            os.environ.pop(name, None)
        self.tmp.cleanup()

    def files(self):
        return list(Path(os.environ["MINDMATE_VAULT_DIR"]).glob("*.enc"))

    def test_roundtrip_and_ciphertext_hides_content(self):
        doc_id = vault.save_document(self.alice, "report.txt", SECRET, "Blood test", "Medical")
        self.assertEqual(vault.read_decrypted(self.alice, doc_id), SECRET)
        raw = self.files()[0].read_bytes()
        self.assertTrue(raw.startswith(vault.MAGIC))
        self.assertNotIn(b"Blood group", raw)
        self.assertNotIn(b"Patient", raw)

    def test_other_user_cannot_touch_documents(self):
        doc_id = vault.save_document(self.alice, "a.txt", SECRET)
        self.assertEqual(vault.list_documents(self.bob), [])
        self.assertIsNone(vault.get_document(self.bob, doc_id))
        with self.assertRaises(vault.VaultError):
            vault.read_decrypted(self.bob, doc_id)
        with self.assertRaises(vault.VaultError):
            vault.replace_document(self.bob, doc_id, "x.txt", b"evil")
        self.assertFalse(vault.rename_document(self.bob, doc_id, "hacked"))
        self.assertFalse(vault.delete_document(self.bob, doc_id))
        self.assertEqual(len(self.files()), 1, "Bob's failed delete must NOT remove Alice's encrypted file")
        self.assertEqual(vault.read_decrypted(self.alice, doc_id), SECRET)

    def test_wrong_master_key_cannot_decrypt(self):
        doc_id = vault.save_document(self.alice, "a.txt", SECRET)
        os.environ["MINDMATE_VAULT_KEY"] = KEY_B
        with self.assertRaises(vault.VaultError):
            vault.read_decrypted(self.alice, doc_id)

    def test_encrypted_files_cannot_be_swapped_between_records(self):
        first = vault.save_document(self.alice, "one.txt", b"first secret")
        second = vault.save_document(self.alice, "two.txt", b"second secret")
        a, b = (Path(os.environ["MINDMATE_VAULT_DIR"]) / f"{i}.enc" for i in (first, second))
        a.write_bytes(b.read_bytes())                     # copy file two over file one
        with self.assertRaises(vault.VaultError):
            vault.read_decrypted(self.alice, first)

    def test_tampering_is_detected(self):
        doc_id = vault.save_document(self.alice, "a.txt", SECRET)
        path = self.files()[0]
        blob = bytearray(path.read_bytes())
        blob[-1] ^= 1
        path.write_bytes(bytes(blob))
        with self.assertRaises(vault.VaultError):
            vault.read_decrypted(self.alice, doc_id)

    def test_rejects_fake_oversize_and_unknown_files(self):
        for name, data in [("virus.pdf", b"MZ not a pdf"), ("x.exe", b"hello"), ("empty.txt", b""),
                           ("fake.png", b"not an image"), ("big.txt", b"a" * (vault.MAX_FILE_BYTES + 1))]:
            with self.assertRaises(vault.VaultError, msg=name):
                vault.save_document(self.alice, name, data)
        self.assertEqual(self.files(), [])

    def test_quota_on_document_count(self):
        original = vault.MAX_DOCS_PER_USER
        vault.MAX_DOCS_PER_USER = 2
        try:
            vault.save_document(self.alice, "1.txt", b"one")
            vault.save_document(self.alice, "2.txt", b"two")
            with self.assertRaises(vault.VaultError):
                vault.save_document(self.alice, "3.txt", b"three")
            vault.save_document(self.bob, "1.txt", b"bob is not affected")
        finally:
            vault.MAX_DOCS_PER_USER = original

    def test_replace_keeps_id_and_updates_content(self):
        doc_id = vault.save_document(self.alice, "v1.txt", b"version one", "Plan", "Work")
        vault.replace_document(self.alice, doc_id, "v2.txt", b"version two is longer")
        doc = vault.get_document(self.alice, doc_id)
        self.assertEqual((doc.title, doc.category, doc.original_name, doc.size), ("Plan", "Work", "v2.txt", 21))
        self.assertEqual(vault.read_decrypted(self.alice, doc_id), b"version two is longer")
        self.assertEqual(len(self.files()), 1)

    def test_rename_category_and_validation(self):
        doc_id = vault.save_document(self.alice, "a.txt", b"x")
        self.assertTrue(vault.rename_document(self.alice, doc_id, "  New\n name ", "Identity"))
        doc = vault.get_document(self.alice, doc_id)
        self.assertEqual((doc.title, doc.category), ("New name", "Identity"))
        self.assertTrue(vault.rename_document(self.alice, doc_id, "Again", "not-a-category"))
        self.assertEqual(vault.get_document(self.alice, doc_id).category, "Other")
        self.assertFalse(vault.rename_document(self.alice, doc_id, "   "))

    def test_delete_removes_record_and_file(self):
        doc_id = vault.save_document(self.alice, "a.txt", b"x")
        self.assertTrue(vault.delete_document(self.alice, doc_id))
        self.assertEqual(self.files(), [])
        self.assertIsNone(vault.get_document(self.alice, doc_id))

    def test_search_and_category_filter_are_literal_and_private(self):
        vault.save_document(self.alice, "x.txt", b"1", "Heart report 100%", "Medical")
        vault.save_document(self.alice, "y.txt", b"2", "Electricity bill", "Bills & Finance")
        vault.save_document(self.bob, "z.txt", b"3", "Heart secrets", "Medical")
        self.assertEqual([d.title for d in vault.list_documents(self.alice, query="heart")], ["Heart report 100%"])
        self.assertEqual([d.title for d in vault.list_documents(self.alice, query="100%")], ["Heart report 100%"])
        self.assertEqual(vault.list_documents(self.alice, query="_"), [])
        self.assertEqual([d.title for d in vault.list_documents(self.alice, category="Bills & Finance")], ["Electricity bill"])
        self.assertEqual(len(vault.list_documents(self.alice, category="All")), 2)

    def test_path_tricks_in_ids_and_names_are_harmless(self):
        for bad in ("../../etc/passwd", "..\\x", "", "a" * 500, "' OR 1=1 --"):
            self.assertIsNone(vault.get_document(self.alice, bad))
            self.assertFalse(vault.delete_document(self.alice, bad))
            with self.assertRaises(vault.VaultError):
                vault.read_decrypted(self.alice, bad)
        doc_id = vault.save_document(self.alice, "../../evil.txt", b"data")
        self.assertEqual(vault.get_document(self.alice, doc_id).original_name, "evil.txt")
        self.assertEqual(len(self.files()), 1)

    def test_missing_or_bad_key_refuses_to_work(self):
        with patch.object(
            vault,
            "_setting",
            side_effect=lambda name: os.getenv(name, "")
        ):
            os.environ.pop("MINDMATE_VAULT_KEY", None)

            self.assertIn("not set up", vault.key_problem())

            with self.assertRaises(vault.VaultError):
                vault.save_document(self.alice, "a.txt", b"x")

            os.environ["MINDMATE_VAULT_KEY"] = "too-short"

            self.assertNotEqual(vault.key_problem(), "")
            self.assertEqual(self.files(), [])

    def test_activity_log_records_actions_without_file_contents(self):
        doc_id = vault.save_document(self.alice, "a.txt", SECRET)
        vault.rename_document(self.alice, doc_id, "Renamed")
        vault.delete_document(self.alice, doc_id)
        actions = [row[0] for row in vault.list_events(self.alice)]
        self.assertEqual(actions, ["delete", "rename", "upload"])
        self.assertEqual(vault.list_events(self.bob), [])
        self.assertFalse(any("Patient" in str(row) for row in vault.list_events(self.alice)))

    def test_old_database_without_categories_is_upgraded(self):
        import sqlite3
        Path(os.environ["MINDMATE_VAULT_DB"]).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(os.environ["MINDMATE_VAULT_DB"])
        conn.execute("CREATE TABLE vault_items (id TEXT PRIMARY KEY, user_key TEXT NOT NULL, title TEXT NOT NULL, "
                     "original_name TEXT NOT NULL, ext TEXT NOT NULL, size INTEGER NOT NULL, "
                     "created_at REAL NOT NULL, updated_at REAL NOT NULL)")
        conn.commit()
        conn.close()
        doc_id = vault.save_document(self.alice, "a.txt", b"x", "Upgraded")
        self.assertEqual(vault.get_document(self.alice, doc_id).category, "Other")


if __name__ == "__main__":
    unittest.main()
