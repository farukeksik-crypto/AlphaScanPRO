def test_imports():
    from engine.cache_engine import CacheEngine
    from engine.data_engine import DataEngine
    from database.db import Database

    assert CacheEngine is not None
    assert DataEngine is not None
    assert Database is not None
