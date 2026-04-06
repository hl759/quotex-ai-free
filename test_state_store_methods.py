import unittest
from state_store import StateStore


class StateStoreMethodTests(unittest.TestCase):
    def test_storage_governance_methods_exist_on_instance(self):
        store = StateStore(db_path=':memory:')
        self.assertTrue(callable(getattr(store, 'prune_scans', None)))
        self.assertTrue(callable(getattr(store, 'prune_collection', None)))
        self.assertTrue(callable(getattr(store, 'vacuum_if_sqlite', None)))


if __name__ == '__main__':
    unittest.main()
