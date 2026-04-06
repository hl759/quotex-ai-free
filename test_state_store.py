import os
import tempfile
import unittest

from state_store import StateStore


class StateStoreSmokeTest(unittest.TestCase):
    def test_methods_exist_and_basic_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, 'state.db')
            store = StateStore(db_path=db_path, database_url='')
            store.set_json('hello', {'a': 1})
            self.assertEqual(store.get_json('hello', {}), {'a': 1})
            self.assertTrue(hasattr(store, 'prune_scans'))
            self.assertTrue(hasattr(store, 'prune_collection'))
            self.assertTrue(hasattr(store, 'vacuum_if_sqlite'))
            store.append_scan({'signals': [], 'current_decision': {}}, 1)
            self.assertGreaterEqual(store.max_scan_count(), 1)
            self.assertIsInstance(store.prune_scans(keep_latest=10, max_age_days=1), int)
            self.assertIsInstance(store.prune_collection('journal_trades', keep_latest=10, max_age_days=1), int)
            self.assertTrue(store.vacuum_if_sqlite())


if __name__ == '__main__':
    unittest.main()
