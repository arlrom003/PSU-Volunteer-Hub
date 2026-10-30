"""Explicit, rerunnable MySQL upgrade for existing annual-plan databases."""
from sqlalchemy import inspect, text

from app.models.annual_plan import AnnualActivityMapping, AnnualGoalProposal


def migrate_annual_goals(engine, database, dry_run=False):
    if engine.dialect.name not in ('mysql', 'mariadb'):
        raise ValueError('This migration supports MySQL/MariaDB only.')
    if not database or database != engine.url.database:
        raise ValueError('Database name does not match the configured target; nothing changed.')
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not {'annual_plans', 'annual_indicators', 'annual_targets', 'annual_results'} <= tables:
        raise ValueError('Apply the initial annual-plan schema before this workflow migration.')
    quote = engine.dialect.identifier_preparer.quote
    statements = []
    additions = {
        'annual_targets': {'comparison_rule': "VARCHAR(4) NOT NULL DEFAULT 'gte'",
                           'is_active': 'BOOLEAN NOT NULL DEFAULT TRUE'},
        'annual_results': {'coverage_start': 'DATE NULL', 'coverage_end': 'DATE NULL', 'sex_counts': 'JSON NULL'},
    }
    for table, columns in additions.items():
        present = {column['name'] for column in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name not in present:
                statements.append(f'ALTER TABLE {quote(table)} ADD COLUMN {quote(name)} {ddl}')
    for foreign_key in inspector.get_foreign_keys('annual_targets'):
        if foreign_key['constrained_columns'] == ['campus_id']:
            if foreign_key.get('options', {}).get('ondelete', 'RESTRICT').upper() not in ('RESTRICT', 'NO ACTION'):
                name = quote(foreign_key['name'])
                statements.append(f'ALTER TABLE annual_targets DROP FOREIGN KEY {name}, '
                                  'ADD CONSTRAINT fk_annual_targets_campus_workflow FOREIGN KEY (campus_id) REFERENCES campuses(id) ON DELETE RESTRICT')
            break
    else:
        statements.append('ALTER TABLE annual_targets ADD CONSTRAINT fk_annual_targets_campus '
                          'FOREIGN KEY (campus_id) REFERENCES campuses(id) ON DELETE RESTRICT')
    missing_tables = [model.__table__ for model in (AnnualActivityMapping, AnnualGoalProposal)
                      if model.__tablename__ not in tables]
    plan = [*statements, *[f'CREATE TABLE {table.name}' for table in missing_tables]]
    if not dry_run:
        # MySQL DDL commits independently. Inspection makes interrupted runs resumable.
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
            for table in missing_tables:
                table.create(connection, checkfirst=True)
    return plan
