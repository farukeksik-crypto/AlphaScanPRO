from database.db import Database
from database.robot_migrations import migrate_database_object
from engine.market_accounts import MARKET_ACCOUNTS
from engine.paper_capital_manager import PaperCapitalManager


def test_targets_are_high_capacity():
    assert MARKET_ACCOUNTS["BIST"]["starting_balance"] == 25_000_000.0
    assert MARKET_ACCOUNTS["KRIPTO"]["starting_balance"] == 1_000_000.0
    assert MARKET_ACCOUNTS["EMTIA"]["starting_balance"] == 1_000_000.0


def test_upgrade_preserves_profit_and_adds_only_capital(tmp_path):
    db = Database(tmp_path / "capital.db")
    migrate_database_object(db)
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE robot_accounts
            SET starting_balance=1000000, balance=900000,
                daily_profit=-10000, total_profit=-100000, enabled=1
            WHERE account_id='bist_main'
            """
        )
        connection.commit()
    result = {x.account_id: x for x in PaperCapitalManager(db).apply_targets()}["bist_main"]
    assert result.added_capital == 24_000_000.0
    with db.connect() as connection:
        row = connection.execute(
            "SELECT starting_balance,balance,daily_profit,total_profit,enabled FROM robot_accounts WHERE account_id='bist_main'"
        ).fetchone()
    assert row == (25_000_000.0, 24_900_000.0, -10_000.0, -100_000.0, 1)


def test_upgrade_is_idempotent(tmp_path):
    db = Database(tmp_path / "capital.db")
    migrate_database_object(db)
    manager = PaperCapitalManager(db)
    manager.apply_targets()
    second = manager.apply_targets()
    assert all(not item.changed for item in second)
    assert all(item.added_capital == 0 for item in second)
