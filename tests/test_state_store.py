from alpha_hive.storage.state_store import get_state_store

def test_state_store_roundtrip():
    store = get_state_store()
    store.set_json("hello", {"a": 1})
    assert store.get_json("hello") == {"a": 1}
