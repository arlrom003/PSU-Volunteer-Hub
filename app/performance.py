"""Request-local query measurement and reuse; never a cross-user cache."""
from hashlib import sha256
import logging
from time import perf_counter

from flask import g, has_request_context, request
from sqlalchemy import event


def request_value(key, load):
    if not has_request_context():
        return load()
    values = g.setdefault('_performance_values', {})
    if key not in values:
        values[key] = load()
    return values[key]


def init_performance(app, db):
    if app.config['PERFORMANCE_METRICS_ENABLED']:
        app.logger.setLevel(logging.INFO)
    @app.before_request
    def start_measurement():
        g._performance_values = {}
        g.pop('_request_measurement', None)
        if app.config['PERFORMANCE_METRICS_ENABLED'] and request.endpoint != 'static':
            g._request_measurement = dict(start=perf_counter(), queries=0, sql_ms=0.0, slow=[])

    def before_query(connection, cursor, statement, parameters, context, executemany):
        if has_request_context() and hasattr(g, '_request_measurement'):
            context._performance_started = perf_counter()

    def after_query(connection, cursor, statement, parameters, context, executemany):
        started = getattr(context, '_performance_started', None)
        if started is None or not has_request_context() or not hasattr(g, '_request_measurement'):
            return
        elapsed = (perf_counter() - started) * 1000
        measurement = g._request_measurement
        measurement['queries'] += 1
        measurement['sql_ms'] += elapsed
        if elapsed >= app.config['PERFORMANCE_SLOW_QUERY_MS']:
            fingerprint = sha256(' '.join(statement.split()).encode()).hexdigest()[:16]
            measurement['slow'].append((fingerprint, round(elapsed, 2)))

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', before_query)
        event.listen(db.engine, 'after_cursor_execute', after_query)

    @app.after_request
    def finish_measurement(response):
        measurement = getattr(g, '_request_measurement', None)
        if measurement:
            app.logger.info('request_performance endpoint=%s status=%s elapsed_ms=%.2f queries=%s sql_ms=%.2f slow=%s',
                            request.endpoint, response.status_code,
                            (perf_counter() - measurement['start']) * 1000,
                            measurement['queries'], measurement['sql_ms'], measurement['slow'])
        return response
