"""Additive indexes; execution is an explicit operator step, never app startup."""
import click
from flask.cli import with_appcontext
from sqlalchemy import Index, MetaData, Table, inspect
from app.models import db


INDEXES = {
    'events': [('date', 'id'), ('campus_id', 'date', 'id')],
    'registrations': [('event_id', 'status', 'user_id'), ('user_id', 'registered_at', 'id')],
    'attendance': [('event_id', 'status', 'user_id')],
    'notifications': [('user_id', 'created_at', 'id'), ('user_id', 'is_read')],
    'auth_security_events': [('action', 'subject_hash', 'created_at')],
}


def index_name(table, columns):
    return 'ix_perf_' + table + '_' + '_'.join(columns)


def migrate_indexes(engine, database, dry_run=True, rollback=False):
    if not database or database != engine.url.database:
        raise ValueError('Database name does not match the configured target.')
    inspector = inspect(engine)
    if not set(INDEXES) <= set(inspector.get_table_names()):
        raise ValueError('Required application tables are missing.')
    changes = []
    for table, definitions in INDEXES.items():
        existing = inspector.get_indexes(table)
        known = {column['name'] for column in inspector.get_columns(table)}
        for columns in definitions:
            if not set(columns) <= known:
                raise ValueError(f'Required columns are missing from {table}.')
            label = index_name(table, columns)
            named = next((item for item in existing if item['name'] == label), None)
            if named and tuple(named['column_names']) != columns:
                raise ValueError(f'Unexpected definition for {label}; review it before migrating.')
            if rollback:
                if named:
                    changes.append(('DROP', table, columns, label))
            elif not any(tuple(item['column_names'][:len(columns)]) == columns for item in existing):
                changes.append(('CREATE', table, columns, label))
        if rollback and engine.dialect.name in ('mysql', 'mariadb'):
            dropping = {label for action, name, columns, label in changes if name == table and action == 'DROP'}
            retained = [tuple(item['column_names']) for item in existing if item['name'] not in dropping]
            retained.append(tuple(inspector.get_pk_constraint(table)['constrained_columns']))
            for foreign_key in inspector.get_foreign_keys(table):
                columns = tuple(foreign_key['constrained_columns'])
                if any(index[:len(columns)] == columns for index in retained):
                    continue
                label = 'ix_fk_' + table + '_' + '_'.join(columns)
                if any(item['name'] == label for item in existing):
                    raise ValueError(f'Unexpected foreign-key support index {label}.')
                changes.insert(0, ('CREATE', table, columns, label))
                retained.append(columns)
    if not dry_run:
        with engine.begin() as connection:
            if engine.dialect.name in ('mysql', 'mariadb'):
                connection.exec_driver_sql('SET SESSION lock_wait_timeout=5')
                connection.exec_driver_sql('SET SESSION innodb_lock_wait_timeout=5')
            for action, table, columns, label in changes:
                reflected = Table(table, MetaData(), autoload_with=connection, resolve_fks=False)
                index = next((item for item in reflected.indexes if item.name == label), None)
                if index is None:
                    index = Index(label, *(reflected.c[column] for column in columns))
                index.create(connection) if action == 'CREATE' else index.drop(connection)
    return [f'{action} INDEX {label} ON {table} ({", ".join(columns)})' for action, table, columns, label in changes]


@click.command('migrate-performance-indexes')
@click.option('--database', required=True)
@click.option('--dry-run', is_flag=True)
@click.option('--rollback', is_flag=True, help='Remove only indexes introduced by this migration.')
@with_appcontext
def migrate_performance_indexes(database, dry_run, rollback):
    click.echo(f'Target: {db.engine.url.host or "local"}/{database}')
    try:
        changes = migrate_indexes(db.engine, database, dry_run=True, rollback=rollback)
        for statement in changes:
            click.echo(statement)
        if not dry_run and changes:
            phrase = f'{"REMOVE" if rollback else "ADD"} PERFORMANCE INDEXES {database}'
            if click.prompt(f'After backup verification, type {phrase}') != phrase:
                raise ValueError('Confirmation did not match; nothing changed.')
            migrate_indexes(db.engine, database, dry_run=False, rollback=rollback)
        click.echo(f'{len(changes)} index change(s){" planned" if dry_run else " applied"}. MySQL DDL commits independently.')
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
