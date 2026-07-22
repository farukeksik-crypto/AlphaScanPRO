from database.db import Database
from database.robot_migrations import migrate_database_object
from engine.background_orchestrator import BackgroundOrchestrator
from engine.market_accounts import account_for_context, all_account_profiles
from engine.paper_capital_manager import PaperCapitalManager


class DummySettings:
    max_saved_rows_per_run = 100


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class DummyDataEngine:
    pass


def test_bist_universes_map_to_independent_accounts():
    assert account_for_context("BIST", "Katılım Tüm")["account_id"] == "bist_katilim"
    assert account_for_context("BIST", "Katilim Tum")["account_id"] == "bist_katilim"
    assert account_for_context("BIST", "Arındırma 0")["account_id"] == "bist_arindirma0"
    assert account_for_context("BIST", "arindirma_0")["account_id"] == "bist_arindirma0"
    assert account_for_context("BIST", "Tüm BIST")["account_id"] == "bist_all"
    assert account_for_context("KRIPTO", "Hepsi")["account_id"] == "crypto_main"
    assert account_for_context("EMTIA", "Hepsi")["account_id"] == "commodity_main"


def test_migration_supports_multiple_accounts_for_same_market(tmp_path):
    db = Database(tmp_path / "multi_accounts.db")
    migrate_database_object(db)
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT account_id, market, starting_balance FROM robot_accounts ORDER BY account_id"
        ).fetchall()
    accounts = {row[0]: (row[1], float(row[2])) for row in rows}
    assert accounts["bist_katilim"] == ("BIST", 10_000_000.0)
    assert accounts["bist_arindirma0"] == ("BIST", 10_000_000.0)
    assert accounts["bist_all"] == ("BIST", 25_000_000.0)
    assert sum(1 for _, market, _ in rows if market == "BIST") >= 4


def test_capital_manager_creates_all_profiles(tmp_path):
    db = Database(tmp_path / "capital.db")
    migrate_database_object(db)
    results = PaperCapitalManager(db).apply_targets()
    result_ids = {item.account_id for item in results}
    expected_ids = {item["account_id"] for item in all_account_profiles()}
    assert result_ids == expected_ids


def test_orchestrator_selects_account_by_universe(tmp_path):
    db = Database(tmp_path / "orchestrator.db")
    migrate_database_object(db)
    orchestrator = BackgroundOrchestrator(
        db, DummyDataEngine(), {}, DummySettings(), DummyLogger()
    )
    assert orchestrator._robot_for_market("BIST", "Katılım Tüm").account_id == "bist_katilim"
    assert orchestrator._robot_for_market("BIST", "Arındırma 0").account_id == "bist_arindirma0"
    assert orchestrator._robot_for_market("BIST", "Tüm BIST").account_id == "bist_all"
    assert orchestrator._robot_for_market("KRIPTO", "Hepsi").account_id == "crypto_main"
