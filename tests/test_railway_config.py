"""Regression checks for the explicit Railway build boundary and startup policy."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_railway_uses_production_docker_startup_without_seeds():
    docker = (ROOT / 'Dockerfile').read_text()
    assert not (ROOT / 'railway.json').exists()
    assert 'wsgi:app' in docker and '${PORT:-8000}' in docker
    assert '--workers 1' in docker
    assert 'init-production' not in docker and 'seed-demo' not in docker
    assert '/data/private' in docker and 'ln -s /data/public /app/static/uploads' in docker
    assert 'COPY . ' not in docker


def test_build_context_excludes_real_data_and_history():
    ignores = (ROOT / '.dockerignore').read_text().splitlines()
    assert ignores[0] == '*'
    for path in ('static/uploads/', '.env', '.git/', 'Database/', 'instance/'):
        assert path in ignores
    assert '!migrations/' in ignores and '!migrations/*.sql' in ignores
    assert 'COPY migrations ./migrations' in (ROOT / 'Dockerfile').read_text()
    for line in (ROOT / 'Dockerfile').read_text().splitlines():
        if line.startswith('COPY '):
            assert not any(value in line for value in ('Database', 'instance', '.env', '.git'))
