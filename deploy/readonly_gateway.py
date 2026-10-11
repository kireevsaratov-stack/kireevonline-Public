"""Шлюз ТОЛЬКО ДЛЯ ЧТЕНИЯ для Claude на сервере kireevonline.ru.

Ставится один раз командой Романа (deploy/setup_readonly.py) в /home/user/ro-gate.py
и привязывается к отдельному ключу Claude в ~/.ssh/authorized_keys через command="…".
Что бы ни прислали по этому ключу, сервер запускает только этот файл, а он умеет
лишь читать. Шелл, запись файлов, git push, scp, rsync по этому ключу невозможны.

Действия: state, status, readlog, medialist, dbstream, mediatar (список файлов на stdin).
"""

import hashlib
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True

GATE_VERSION = 1
HOME = os.environ.get('KO_GATE_HOME') or os.path.expanduser('~')
DOMAIN = HOME + '/domains/kireevonline.ru'
APP = DOMAIN + '/gallery'
DB = APP + '/db.sqlite3'
MEDIA = os.path.realpath(DOMAIN + '/public_html/media')
SNAP = HOME + '/deploy-backups'


def result(data):
    data.setdefault('ok', True)
    data['gate_version'] = GATE_VERSION
    sys.stdout.write('\nKO_RESULT ' + json.dumps(data) + '\n')


def deny(what):
    sys.stderr.write('Запрещено шлюзом только-для-чтения: %s\n' % what[:200])
    sys.exit(3)


def read_cmd(args):
    p = subprocess.Popen(args, cwd=APP, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    out, _ = p.communicate()
    return p.returncode, out.strip()


def act_state():
    _, head = read_cmd(['git', 'rev-parse', 'HEAD'])
    _, dirty = read_cmd(['git', 'diff', '--name-only', 'HEAD'])
    code, url = read_cmd(['git', 'config', '--get', 'remote.origin.url'])
    code_dj, dj = read_cmd([sys.executable, '-B', '-c', 'import django; print(django.get_version())'])
    st = os.stat(DB)
    result(
        {
            'head': head,
            'dirty': [line for line in dirty.splitlines() if line.strip()],
            'origin_token': code == 0 and '@' in url,
            'django': dj if code_dj == 0 else None,
            'python': sys.version.split()[0],
            'db_size': st.st_size,
            'db_mtime': int(st.st_mtime),
        }
    )


def act_status():
    count, size = 0, 0
    for root, _, names in os.walk(MEDIA):
        for n in names:
            count += 1
            size += os.path.getsize(os.path.join(root, n))
    snaps = sorted(os.listdir(SNAP)) if os.path.isdir(SNAP) else []
    try:
        _, quota = read_cmd(['quota', '-s'])
    except OSError:
        quota = ''
    result(
        {
            'media_files': count,
            'media_mb': round(size / 1e6),
            'snapshots': snaps,
            'quota': quota.splitlines()[-2:] if quota else [],
        }
    )


def act_readlog():
    path = SNAP + '/deploy-log.tsv'
    lines = []
    if os.path.exists(path):
        with open(path) as f:
            lines = [line.rstrip('\n') for line in f if line.strip()][-50:]
    result({'lines': lines})


def act_medialist():
    files = []
    for root, _, names in os.walk(MEDIA):
        for n in names:
            full = os.path.join(root, n)
            files.append([os.path.relpath(full, MEDIA), os.path.getsize(full)])
    result({'files': files})


def act_dbstream():
    """Сырые байты базы в stdout под разделяемой блокировкой SQLite (запись в это
    время ждёт), sha256 — в stderr. Ничего не создаёт на сервере."""
    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True, isolation_level=None)
    if con.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal':
        deny('база в режиме WAL, потоковая копия невозможна')
    con.execute('BEGIN')
    con.execute('SELECT count(*) FROM sqlite_master').fetchone()
    h = hashlib.sha256()
    out = sys.stdout.buffer
    with open(DB, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
            out.write(chunk)
    out.flush()
    con.execute('ROLLBACK')
    con.close()
    sys.stderr.write('KO_SHA256 %s\n' % h.hexdigest())


def act_mediatar():
    """tar-поток (в stdout) с файлами из media по списку (имена через \\0 на stdin)."""
    names = [n for n in sys.stdin.buffer.read().decode('utf-8').split('\0') if n]
    safe = []
    for rel in names:
        full = os.path.realpath(os.path.join(MEDIA, rel))
        if os.path.isabs(rel) or not full.startswith(MEDIA + os.sep) or not os.path.isfile(full):
            deny('файл вне папки фото или не найден: ' + rel)
        safe.append((full, rel))
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as tar:
        for full, rel in safe:
            tar.add(full, arcname=rel, recursive=False)


ACTIONS = {
    'state': act_state,
    'status': act_status,
    'readlog': act_readlog,
    'medialist': act_medialist,
    'dbstream': act_dbstream,
    'mediatar': act_mediatar,
}


def main():
    raw = os.environ.get('SSH_ORIGINAL_COMMAND', '')
    try:
        parts = shlex.split(raw)
    except ValueError:
        deny(raw)
    if len(parts) != 1 or parts[0] not in ACTIONS:
        deny(raw or '(вход без команды)')
    ACTIONS[parts[0]]()


if __name__ == '__main__':
    main()
