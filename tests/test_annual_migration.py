"""Existing MySQL annual tables must be upgraded explicitly and rerunnably."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects.mysql import dialect

from app.annual_migration import migrate_annual_goals


def test_upgrade_missing_columns_and_generated_foreign_key_then_noop(monkeypatch):
    engine = SimpleNamespace(dialect=dialect(), url=SimpleNamespace(database='test_goals'), begin=MagicMock())
    inspector = MagicMock()
    inspector.get_table_names.return_value = ['annual_plans', 'annual_indicators', 'annual_targets',
        'annual_results', 'annual_activity_mappings', 'annual_goal_proposals']
    inspector.get_columns.return_value = [{'name': 'id'}]
    inspector.get_foreign_keys.return_value = [dict(name='annual_targets_ibfk_2',
        constrained_columns=['campus_id'], options={'ondelete':'SET NULL'})]
    monkeypatch.setattr('app.annual_migration.inspect', lambda _: inspector)
    plan = migrate_annual_goals(engine, 'test_goals', dry_run=True)
    assert len(plan) == 6
    assert any('comparison_rule' in sql and "DEFAULT 'gte'" in sql for sql in plan)
    assert any('DROP FOREIGN KEY annual_targets_ibfk_2' in sql and 'fk_annual_targets_campus_workflow' in sql for sql in plan)
    engine.begin.assert_not_called()
    assert migrate_annual_goals(engine, 'test_goals') == plan
    assert engine.begin.return_value.__enter__.return_value.execute.call_count == 6
    inspector.get_columns.return_value = [{'name': name} for name in ['comparison_rule', 'is_active', 'coverage_start', 'coverage_end', 'sex_counts']]
    inspector.get_foreign_keys.return_value = [dict(name='fk_annual_targets_campus_workflow',
        constrained_columns=['campus_id'], options={})]
    assert migrate_annual_goals(engine, 'test_goals', dry_run=True) == []


def test_wrong_database_is_rejected_before_inspection(monkeypatch):
    engine = SimpleNamespace(dialect=dialect(), url=SimpleNamespace(database='intended_database'))
    inspector = MagicMock()
    monkeypatch.setattr('app.annual_migration.inspect', inspector)
    with pytest.raises(ValueError, match='does not match'):
        migrate_annual_goals(engine, 'wrong_database')
    inspector.assert_not_called()
