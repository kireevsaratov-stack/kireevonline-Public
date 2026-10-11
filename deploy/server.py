"""Общее для скриптов в deploy/ (связь с сервером).

Два канала связи с сервером:
- ОСНОВНОЙ (ключ Романа, ~/.ssh/id_ed25519): меняет сервер. Им пользуются только
  deploy.py, rollback.py и setup_readonly.py, их запускает только Роман.
  Claude эти скрипты запускать не может (блокировка ~/.claude/hooks/kireevonline-guard.sh).
- ТОЛЬКО ЧТЕНИЕ (ключ Claude, ~/.ssh/kireevonline_readonly): сервер пускает по нему
  лишь в шлюз ro-gate.py (deploy/readonly_gateway.py), который умеет только читать.
  Им пользуются status.py и backup.py — их можно запускать и Роману, и Claude.

Тестовый режим для проверки скриптов на Mac, без сети:
    KO_FAKE_SERVER=<папка-копия сервера>  KO_FAKE_PY=<python с Django>
    KO_SITE_URL=http://127.0.0.1:<порт>   [KO_FAKE_RESTART_FILE=config/urls.py]
"""

import datetime
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # .../kireevonline/gallery
BACKUPS = REPO.parent / 'backups'  # .../kireevonline/backups
MAC_LOG = BACKUPS / 'deploy-log.tsv'

SSH_TARGET = 'user@kireevonline.ru'
SITE_URL = 'https://kireevonline.ru'
REMOTE_HOME = '/home/user'
REMOTE_PY = REMOTE_HOME + '/python/bin/python'
SSH_OPTS = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20', '-o', 'ServerAliveInterval=15']
RO_KEY = Path.home() / '.ssh' / 'kireevonline_readonly'
RO_COMMENT = 'claude-readonly@kireevonline'


# ---------- вывод ----------


def say(text=''):
    print(text, flush=True)


def ok(text):
    say('  ✔ ' + text)


def warn(text):
    say('  ⚠ ' + text)


def fail(text):
    say('')
    say('✖ ' + text)
    sys.exit(1)


def confirm(question):
    say('')
    try:
        answer = input(question + ' Напишите «да» и нажмите Enter: ')
    except EOFError:
        return False
    return answer.strip().lower() == 'да'


def now_stamp():
    return datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------- git на Mac ----------


def git(*args, check=True):
    r = subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode != 0:
        fail('git %s не сработал:\n%s' % (' '.join(args), (r.stderr or r.stdout).strip()))
    return r.stdout.strip()


def git_ok(*args):
    return subprocess.run(['git', *args], cwd=REPO, capture_output=True).returncode == 0


def describe(sha):
    """«abc1234 от 05.06.2026 — описание» для показа человеку."""
    return git('log', '-1', '--format=%h от %ad — %s', '--date=format:%d.%m.%Y %H:%M', sha)


def changed_files(old, new):
    return [p for p in git('diff', '--name-only', old, new).splitlines() if p]


def change_flags(files):
    return {
        'migr': any(p.startswith('photos/migrations/') for p in files),
        'reqs': 'requirements.txt' in files,
        # новые библиотеки (например, Django) приносят свои стили — их тоже нужно собрать
        'static': 'requirements.txt' in files or any(p.startswith('static/') or '/static/' in p for p in files),
    }


TEST_PY = Path(os.environ.get('KO_TEST_PY') or REPO.parent / '.venv' / 'bin' / 'python')


# Хостинг — старый Linux (glibc 2.17): готовые сборки библиотек нужны в формате manylinux2014 или старше.
# Собрать библиотеку из исходников сервер не может (так 09.10.2026 не встал Pillow 12.3.0).
SERVER_PLATFORMS = ['manylinux2014_x86_64', 'manylinux_2_17_x86_64', 'manylinux2010_x86_64', 'manylinux1_x86_64']


def check_server_wheels(sha, python_version):
    """Есть ли для всех библиотек версии sha готовые сборки под сервер. Возвращает (да/нет, отчёт).
    Скачивает их на Mac во временную папку — так, как их выбрал бы pip на сервере."""
    import tempfile

    if not TEST_PY.exists():
        return False, 'не найден Python для проверки: %s' % TEST_PY
    reqs = git('show', '%s:requirements.txt' % sha)
    with tempfile.TemporaryDirectory(prefix='kireevonline-wheels-') as tmp:
        req_file = Path(tmp) / 'requirements.txt'
        req_file.write_text(reqs + '\n')
        major_minor = '.'.join(python_version.split('.')[:2])
        args = [str(TEST_PY), '-m', 'pip', 'download', '--quiet', '--no-deps', '--only-binary=:all:',
                '--python-version', major_minor, '--implementation', 'cp', '-d', str(Path(tmp) / 'w'),
                '-r', str(req_file)]  # fmt: skip
        for platform in SERVER_PLATFORMS:
            args += ['--platform', platform]
        r = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[-1500:]
    return True, 'для всех библиотек есть готовые сборки под сервер (Python %s, старый Linux)' % major_minor


def run_tests_at(sha):
    """Автотесты сайта ровно на версии sha — в отдельной временной копии кода, рабочая папка не трогается.
    Возвращает (прошли ли, короткий отчёт)."""
    import tempfile

    if not TEST_PY.exists():
        return False, 'не найден Python с Django для тестов: %s' % TEST_PY
    tmp = tempfile.mkdtemp(prefix='kireevonline-tests-')
    try:
        git('worktree', 'add', '--detach', '--quiet', tmp, sha)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('KO_', 'DJANGO_'))}
        r = subprocess.run(
            [str(TEST_PY), 'manage.py', 'test', 'photos', '--noinput'],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
        summary = re.findall(r'^(Ran \d+ tests? in [\d.]+s)$', r.stderr, re.M)
        if r.returncode != 0:
            return False, r.stderr[-3000:]
        return True, 'автотесты прошли: %s' % (summary[-1] if summary else 'ok')
    except subprocess.TimeoutExpired:
        return False, 'автотесты не уложились в 15 минут'
    finally:
        subprocess.run(['git', 'worktree', 'remove', '--force', tmp], cwd=REPO, capture_output=True)
        subprocess.run(['rm', '-rf', tmp], capture_output=True)


def has_version_marker(sha):
    return git_ok('cat-file', '-e', '%s:config/version.py' % sha)


def last_migration(sha):
    names = git('ls-tree', '--name-only', '%s:photos/migrations' % sha).splitlines()
    names = sorted(n[:-3] for n in names if re.match(r'^\d{4}_.+\.py$', n))
    return names[-1] if names else None


# ---------- сервер ----------

REMOTE_HELPER = r"""
import hashlib, json, os, sqlite3, subprocess, sys

HOME, ACTION, ARGS = sys.argv[1], sys.argv[2], sys.argv[3:]
DOMAIN = HOME + '/domains/kireevonline.ru'
APP = DOMAIN + '/gallery'
WSGI = DOMAIN + '/public_html/site.wsgi'
MEDIA = DOMAIN + '/public_html/media'
SNAP = HOME + '/deploy-backups'
LOG = SNAP + '/deploy-log.tsv'
CLEAN_ORIGIN = 'https://github.com/<владелец>/<приватный-репозиторий>.git'
KEEP = 10


class Fail(Exception):
    def __init__(self, step, output):
        Exception.__init__(self, step)
        self.step, self.output = step, output


def sh(args):
    p = subprocess.Popen(args, cwd=APP, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True)
    out, err = p.communicate()
    return p.returncode, out, err


def run_step(step, args):
    code, out, err = sh(args)
    if code != 0:
        raise Fail(step, (out + err)[-3000:])
    return out


def git(*args):
    return run_step('git ' + args[0], ['git'] + list(args)).strip()


def manage(step, *args):
    return run_step(step, [sys.executable, 'manage.py'] + list(args))


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def db_copy(src_path, dst_path):
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    src.backup(dst)
    dst.close()
    src.close()


def prune(prefix):
    names = sorted(n for n in os.listdir(SNAP) if n.startswith(prefix))
    for n in names[:-KEEP]:
        os.remove(os.path.join(SNAP, n))


def restart():
    os.utime(WSGI, None)
    extra = os.environ.get('KO_FAKE_RESTART_FILE')
    if extra:
        os.utime(os.path.join(APP, extra), None)


def pip_install(requirements):
    # без кэша: квота хостинга 2 ГБ, а кэш pip после одной выкладки занял 56 МБ (09.10.2026)
    run_step('pip install', [sys.executable, '-m', 'pip', 'install', '-q', '--no-cache-dir', '-r', requirements])


def act_state():
    code, url, _ = sh(['git', 'config', '--get', 'remote.origin.url'])
    code_dj, dj, _ = sh([sys.executable, '-c', 'import django; print(django.get_version())'])
    return {
        'head': git('rev-parse', 'HEAD'),
        'dirty': [l for l in git('status', '--porcelain', '--untracked-files=no').splitlines() if l.strip()],
        'origin_token': code == 0 and '@' in url,
        'django': dj.strip() if code_dj == 0 else None,
        'python': sys.version.split()[0],
        'wsgi': os.path.exists(WSGI),
        'db': os.path.exists(APP + '/db.sqlite3'),
        'pending': json.load(open(PENDING)) if os.path.exists(PENDING) else None,
    }


def act_snapshot(stamp, label):
    if not os.path.isdir(SNAP):
        os.makedirs(SNAP)
    notes = []
    code, url, _ = sh(['git', 'config', '--get', 'remote.origin.url'])
    if code == 0 and '@' in url:
        git('remote', 'set-url', 'origin', CLEAN_ORIGIN)
        notes.append('token-removed')
    db = '%s/db_%s_%s.sqlite3' % (SNAP, stamp, label)
    db_copy(APP + '/db.sqlite3', db)
    pip = '%s/pip_%s_%s.txt' % (SNAP, stamp, label)
    # «имя==версия» без ссылок на файлы: pip freeze пишет setuptools хостинга как «@ file:///builddir/…»,
    # и по такому списку библиотеки потом не вернуть (сбой автовозврата 09.10.2026)
    code, out, _ = sh([sys.executable, '-m', 'pip', 'list', '--format=freeze'])
    with open(pip, 'w') as f:
        f.write(out if code == 0 else '')
    prune('db_')
    prune('pip_')
    return {'db': db, 'db_sha256': sha256(db), 'db_size': os.path.getsize(db), 'pip': pip,
            'pip_ok': code == 0, 'notes': notes}


PENDING = SNAP + '/pending-deploy.json'


def act_pending(src, dst, db='', pip='', kind='deploy'):
    # Отметка «операция kind (deploy/rollback) src → dst начата»; db и pip — снимки базы и списка библиотек ДО неё.
    # Если операцию прервут, следующий запуск это увидит: выкладку доделает, откат — вернёт к состоянию до него,
    # в обоих случаях беря снимки, сделанные до прерванной операции.
    with open(PENDING, 'w') as f:
        json.dump({'from': src, 'to': dst, 'db': db, 'pip': pip, 'kind': kind}, f)
    return {}


def act_apply(sha, reqs, migr, static):
    done = []
    git('reset', '--hard', sha)
    done.append('code')
    if reqs == '1':
        pip_install('requirements.txt')
        done.append('pip')
    if migr == '1':
        manage('migrate', 'migrate', '--noinput')
        done.append('migrate')
    if static == '1':
        manage('collectstatic', 'collectstatic', '--noinput')
        done.append('collectstatic')
    restart()
    done.append('restart')
    return {'done': done}


def act_rollback(sha, migrate_to, db_restore, pip_file, static, stamp):
    done = []
    if migrate_to:
        before = '%s/db_%s_before-reverse-migrate.sqlite3' % (SNAP, stamp)
        db_copy(APP + '/db.sqlite3', before)
        try:
            manage('reverse-migrate', 'migrate', 'photos', migrate_to, '--noinput')
        except Fail as e:
            db_copy(before, APP + '/db.sqlite3')  # несколько миграций — не одна транзакция: вернуть как было
            raise Fail('reverse-migrate', e.output + '\n[база возвращена из снимка перед откатом]') from None
        done.append('reverse-migrate')
    if db_restore:
        if not os.path.exists(db_restore):
            raise Fail('db-restore', 'нет файла снимка: ' + db_restore)
        db_copy(APP + '/db.sqlite3', '%s/db_%s_replaced.sqlite3' % (SNAP, stamp))
        db_copy(db_restore, APP + '/db.sqlite3')
        done.append('db-restore')
    git('reset', '--hard', sha)
    done.append('code')
    if pip_file:
        pip_install(pip_file)
        done.append('pip')
    if static == '1':
        manage('collectstatic', 'collectstatic', '--noinput')
        done.append('collectstatic')
    restart()
    done.append('restart')
    return {'done': done}


def act_restart():
    restart()
    return {}


def act_install_gate(gate_b64, pubkey, comment):
    import base64, time
    gate = HOME + '/ro-gate.py'
    ssh_dir = HOME + '/.ssh'
    ak = ssh_dir + '/authorized_keys'
    if not os.path.isdir(ssh_dir):
        os.makedirs(ssh_dir, 0o700)
    if os.path.islink(ak) or os.path.islink(ssh_dir):
        raise Fail('authorized_keys', 'файл ключей устроен хостингом особым образом (ссылка) — ничего не трогаю')
    old = ''
    backup = ''
    if os.path.exists(ak):
        with open(ak) as f:
            old = f.read()
        backup = '%s.bak-%s' % (ak, time.strftime('%Y%m%d-%H%M%S'))
        n = 1
        while os.path.exists(backup):
            n += 1
            backup = '%s.bak-%s-%d' % (ak, time.strftime('%Y%m%d-%H%M%S'), n)
        with open(backup, 'w') as f:
            f.write(old)
        os.chmod(backup, 0o600)
    with open(gate + '.tmp', 'wb') as f:
        f.write(base64.b64decode(gate_b64))
    os.chmod(gate + '.tmp', 0o644)
    os.rename(gate + '.tmp', gate)
    line = ('command="%s -B %s",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty %s'
            % (sys.executable, gate, pubkey.strip()))
    kept = [l for l in old.splitlines() if comment not in l]
    with open(ak + '.tmp', 'w') as f:
        f.write('\n'.join(kept + [line]) + '\n')
    os.chmod(ak + '.tmp', 0o600)
    os.rename(ak + '.tmp', ak)
    return {'backup': backup, 'kept': len(kept), 'before': len(old.splitlines())}


def act_uninstall_gate(comment):
    ak = HOME + '/.ssh/authorized_keys'
    with open(ak) as f:
        kept = [l for l in f.read().splitlines() if comment not in l]
    with open(ak + '.tmp', 'w') as f:
        f.write('\n'.join(kept) + '\n')
    os.chmod(ak + '.tmp', 0o600)
    os.rename(ak + '.tmp', ak)
    return {'kept': len(kept)}


def act_log(*fields):
    if not os.path.isdir(SNAP):
        os.makedirs(SNAP)
    with open(LOG, 'a') as f:
        f.write('\t'.join(fields) + '\n')
    # поля: время, действие, откуда, куда, итог. Сайт в согласованном состоянии (выложено, возвращено,
    # код не передавался) — отметка о незавершённой выкладке больше не нужна; при сбоях — остаётся
    settled = ('OK', 'AUTO_ROLLED_BACK', 'PUSH_FAILED')
    if len(fields) > 4 and fields[1] in ('deploy', 'rollback', 'recover') and fields[4] in settled:
        if os.path.exists(PENDING):
            os.remove(PENDING)
    return {}


def act_readlog():
    if not os.path.exists(LOG):
        return {'lines': []}
    with open(LOG) as f:
        return {'lines': [l.rstrip('\n') for l in f if l.strip()][-50:]}


ACTIONS = {'state': act_state, 'snapshot': act_snapshot, 'pending': act_pending, 'apply': act_apply,
           'rollback': act_rollback, 'log': act_log, 'readlog': act_readlog,
           'install_gate': act_install_gate, 'uninstall_gate': act_uninstall_gate,
           'restart': act_restart}

try:
    result = ACTIONS[ACTION](*ARGS)
    result['ok'] = True
except Fail as e:
    result = {'ok': False, 'step': e.step, 'output': e.output}
except Exception as e:
    result = {'ok': False, 'step': ACTION, 'output': '%s: %s' % (type(e).__name__, e)}
sys.stdout.write('\nKO_RESULT ' + json.dumps(result) + '\n')
"""


def _target():
    """(fake, home, py, site): настоящий сервер или тестовая папка на Mac."""
    if 'KO_FAKE_SERVER' not in os.environ:
        return None, REMOTE_HOME, REMOTE_PY, SITE_URL
    fake = os.environ['KO_FAKE_SERVER'].strip()
    if not fake:
        fail('KO_FAKE_SERVER задан пустым. Ничего не делаю.')
    fake = Path(fake).resolve()
    if not fake.is_dir() or str(fake).startswith('/home/'):
        fail('KO_FAKE_SERVER должен указывать на папку-копию сервера на Mac.')
    py = os.environ.get('KO_FAKE_PY') or fail('В тестовом режиме нужен KO_FAKE_PY.')
    site = os.environ.get('KO_SITE_URL') or fail('В тестовом режиме нужен KO_SITE_URL.')
    return fake, str(fake), py, site


def _parse_result(stdout_bytes, stderr_bytes, what):
    out = stdout_bytes.decode(errors='replace')
    marker = [line for line in out.splitlines() if line.startswith('KO_RESULT ')]
    if not marker:
        err = stderr_bytes.decode(errors='replace').strip()
        if 'Permission denied' in err and what.startswith('шлюз'):
            err += (
                '\nСервер не пускает ключ Claude: доступ только для чтения ещё не настроен.'
                '\nРоман запускает один раз: python3 deploy/setup_readonly.py'
            )
        return {'ok': False, 'step': what, 'output': err or out[-2000:]}
    return json.loads(marker[-1][len('KO_RESULT ') :])


class ReadOnly:
    """Канал ТОЛЬКО ДЛЯ ЧТЕНИЯ: ключ Claude → шлюз ro-gate.py на сервере."""

    def __init__(self):
        self.fake, self.home, self.py, self.site = _target()
        if not self.fake and not RO_KEY.exists():
            fail(
                'Доступ только для чтения ещё не настроен.\nРоман запускает один раз: python3 deploy/setup_readonly.py'
            )

    def _popen(self, action, **kw):
        if self.fake:
            env = dict(os.environ, SSH_ORIGINAL_COMMAND=action, KO_GATE_HOME=self.home)
            return subprocess.Popen([self.py, str(REPO / 'deploy' / 'readonly_gateway.py')], env=env, **kw)
        argv = [
            'ssh',
            '-F',
            '/dev/null',
            '-i',
            str(RO_KEY),
            '-o',
            'IdentitiesOnly=yes',
            '-o',
            'StrictHostKeyChecking=yes',
            '-o',
            'UserKnownHostsFile=' + str(Path.home() / '.ssh' / 'known_hosts'),
            *SSH_OPTS,
            SSH_TARGET,
            action,
        ]
        return subprocess.Popen(argv, **kw)

    def raw(self, action, input_bytes=None):
        p = self._popen(action, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate(input_bytes)
        return p.returncode, out, err

    def call(self, action):
        _, out, err = self.raw(action)
        return _parse_result(out, err, 'шлюз чтения: ' + action)

    def download_db(self, local_path):
        """Копия базы: байты с сервера сразу в файл, сверка sha256 с сервером."""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, 'wb') as f:
            p = self._popen('dbstream', stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.PIPE)
            err = p.communicate()[1].decode(errors='replace')
        m = re.search(r'KO_SHA256 ([0-9a-f]{64})', err)
        if p.returncode != 0 or not m:
            local_path.unlink(missing_ok=True)
            fail('Не удалось скачать базу:\n%s' % err.strip())
        if sha256_file(local_path) != m.group(1):
            local_path.unlink(missing_ok=True)
            fail('Копия базы повредилась при скачивании — запустите ещё раз.')
        return local_path

    def download_media(self, rels, dest):
        import tarfile

        p = self._popen('mediatar', stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.stdin.write(b'\0'.join(r.encode() for r in rels) + b'\0')
        p.stdin.close()
        with tarfile.open(fileobj=p.stdout, mode='r|') as tar:
            tar.extractall(dest, filter='data')
        err = p.stderr.read().decode(errors='replace')
        if p.wait() != 0:
            fail('Скачивание фото прервалось:\n%s\nЗапустите ещё раз — докачается недостающее.' % err)


class Server:
    """ОСНОВНОЙ канал (меняет сервер): только для deploy/rollback/setup_readonly."""

    def __init__(self):
        self.fake, self.home, self.py, self.site = _target()
        self.app = self.home + '/domains/kireevonline.ru/gallery'
        self.media = self.home + '/domains/kireevonline.ru/public_html/media'
        self.push_url = self.app if self.fake else 'ssh://%s%s' % (SSH_TARGET, self.app)

    def _argv(self, remote_cmd):
        if self.fake:
            return ['bash', '-c', remote_cmd]
        return ['ssh', *SSH_OPTS, SSH_TARGET, remote_cmd]

    def run(self, remote_cmd, input_bytes=None, stdout=subprocess.PIPE):
        return subprocess.run(self._argv(remote_cmd), input=input_bytes, stdout=stdout, stderr=subprocess.PIPE)

    def popen(self, remote_cmd, **kw):
        return subprocess.Popen(self._argv(remote_cmd), **kw)

    def helper(self, action, *args):
        cmd = ' '.join(shlex.quote(a) for a in [self.py, '-', self.home, action, *map(str, args)])
        r = self.run(cmd, input_bytes=REMOTE_HELPER.encode())
        return _parse_result(r.stdout, r.stderr, 'связь с сервером')

    def download(self, remote_path, local_path):
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, 'wb') as f:
            r = self.run('cat ' + shlex.quote(remote_path), stdout=f)
        if r.returncode != 0:
            fail('Не удалось скачать %s: %s' % (remote_path, r.stderr.decode(errors='replace')))
        return sha256_file(local_path)

    def push(self, sha):
        env = dict(os.environ, GIT_SSH_COMMAND='ssh ' + ' '.join(SSH_OPTS))
        r = subprocess.run(
            ['git', 'push', '--quiet', self.push_url, '+%s:refs/heads/deploy-incoming' % sha],
            cwd=REPO,
            capture_output=True,
            text=True,
            env=env,
        )
        return r.returncode == 0, (r.stderr or r.stdout).strip()

    def log(self, *fields):
        """Запись в журнал на сервере и на Mac. Возвращает, удалось ли записать на сервере:
        от этой записи зависит откат без явной версии."""
        result = self.helper('log', *fields)
        BACKUPS.mkdir(parents=True, exist_ok=True)
        with open(MAC_LOG, 'a') as f:
            f.write('\t'.join(str(x) for x in fields) + '\n')
        if not result.get('ok'):
            warn(
                'Журнал на сервере не записан (%s). Для отката указывайте версию явно: --to <версия>.'
                % (result.get('output') or '').strip()[:200]
            )
        return bool(result.get('ok'))


def check_server(srv):
    """Только чтение: версия на сервере и отсутствие ручных правок."""
    st = srv.helper('state')
    if not st.get('ok'):
        fail('Не удалось прочитать состояние сервера (%s):\n%s' % (st.get('step'), st.get('output')))
    if st['dirty']:
        fail(
            'На сервере кто-то менял файлы кода вручную:\n  %s\n'
            'Ничего не трогаю. Покажите это сообщение Claude.' % '\n  '.join(st['dirty'])
        )
    if not st['django']:
        fail('На сервере не запускается Python с Django. Ничего не трогаю.')
    if not st['wsgi'] or not st['db']:
        fail('На сервере не найден site.wsgi или база. Ничего не трогаю.')
    return st


def save_db_snapshot_to_mac(srv, snap, label):
    """Кладёт копию снимка базы с сервера в backups/db на Mac и сверяет её."""
    local = BACKUPS / 'db' / ('db_%s.sqlite3' % label)
    digest = srv.download(snap['db'], local)
    if digest != snap['db_sha256']:
        fail('Копия базы на Mac не совпала с сервером. Ничего не выкладываю.')
    return local


# ---------- проверка живого сайта ----------


def _get(url, timeout=45):
    r = subprocess.run(['curl', '-sS', '-i', '--max-time', str(timeout), url], capture_output=True)
    if r.returncode != 0:
        return None, {}, r.stderr.decode(errors='replace').strip()
    head, _, body = r.stdout.partition(b'\r\n\r\n')
    lines = head.decode('latin-1').split('\r\n')
    try:
        status = int(lines[0].split()[1])
    except (IndexError, ValueError):
        return None, {}, 'непонятный ответ сервера'
    headers = {}
    for line in lines[1:]:
        if ':' in line:
            k, v = line.split(':', 1)
            headers[k.strip().lower()] = v.strip()
    return status, headers, body.decode('utf-8', errors='replace')


def _check_pass(site, expect_version, state, request_timeout):
    """Один проход проверки. Страницы, уже ответившие правильно, не перепроверяются:
    через VPN/медленную сеть отдельные запросы зависают на десятки секунд, и требовать,
    чтобы ВСЕ страницы ответили в одном проходе, значит получать ложные откаты."""
    if not state.get('home'):
        status, headers, body = _get(site + '/photos/', request_timeout)
        if status != 200:
            return False, 'главная ответила: %s' % (status or body)
        if 'kireevonline' not in body:
            return False, 'на главной нет ожидаемого содержимого'
        version = headers.get('x-site-version')
        state['waiting_restart'] = bool(expect_version and version != expect_version)
        if state['waiting_restart']:
            return False, 'сайт отвечает версией %s, а ожидается %s' % (version or 'без метки', expect_version)
        # ссылка на альбом: новый вид /album/41/ (с 08.10.2026) или старый /photos/subcategory/41/ — при откате
        m = re.search(r'href="(/album/\d+/|/photos/subcategory/\d+/)"', body)
        state['pages'] = ['/robots.txt', '/sitemap.xml'] + ([m.group(1)] if m else [])
        state['home'] = True
    for page in state['pages']:
        if page in state.setdefault('ok', set()):
            continue
        status, headers, body = _get(site + page, request_timeout)
        if status != 200:
            return False, '%s ответила: %s' % (page, status or body)
        version = headers.get('x-site-version')
        if expect_version and version != expect_version:  # часть процессов сайта ещё на старой версии
            return False, '%s отвечает версией %s, а ожидается %s' % (page, version or 'без метки', expect_version)
        state['ok'].add(page)
    return True, 'главная, альбом, robots.txt и sitemap.xml открываются'


def healthcheck(site, expect_version, timeout=360, request_timeout=45, pause=4, nudge=None, nudge_every=60):
    """Сайт считается рабочим, когда каждая страница хоть раз ответила правильно в течение
    окна (по умолчанию 6 минут). Настоящая поломка (ошибка, нет ответа) окно не пройдёт.
    Хостинг иногда перезапускает сайт с опозданием на минуты: пока сайт исправно отвечает
    старой версией, раз в nudge_every секунд вызывается nudge() — повторный «пинок» перезапуска."""
    if 'KO_FAKE_SERVER' in os.environ:  # тестовый режим на Mac: не ждать по 6 минут
        timeout = float(os.environ.get('KO_FAKE_HEALTH_TIMEOUT', timeout))
    deadline = time.time() + timeout
    state = {}
    last_nudge = time.time()
    while True:
        good, detail = _check_pass(site, expect_version, state, request_timeout)
        if good or time.time() > deadline:
            return good, detail
        if nudge and state.get('waiting_restart') and time.time() - last_nudge >= nudge_every:
            nudge()
            last_nudge = time.time()
        time.sleep(pause)


def recover_interrupted_rollback(srv, pending):
    """Прошлый откат прервали (закрыли окно, оборвалась связь): база могла остаться наполовину возвращённой,
    а код — прежним. Возвращаем сайт целиком к состоянию ДО того отката: код, базу и библиотеки — из снимков,
    сделанных перед ним; затем проверяем живой сайт (аудит 2, 09.10.2026)."""
    src, dst = pending['from'], pending['to']
    warn('Прошлый откат %s → %s был прерван — возвращаю сайт к состоянию до него.' % (src[:7], dst[:7]))
    stamp = now_stamp()
    back = srv.helper('rollback', src, '', pending.get('db', ''), pending.get('pip', ''), '1', stamp)
    if not back.get('ok'):
        srv.log(stamp, 'recover', dst, src, 'FAILED_' + back.get('step', '?'), pending.get('db', ''), '')
        fail(
            'Не удалось вернуть сайт после прерванного отката (%s):\n%s\nПокажите это сообщение Claude.'
            % (back.get('step'), back.get('output'))
        )
    expect = src[:7] if has_version_marker(src) else None
    healthy, detail = healthcheck(srv.site, expect, nudge=lambda: srv.helper('restart'))
    srv.log(stamp, 'recover', dst, src, 'OK' if healthy else 'UNHEALTHY', pending.get('db', ''), '')
    if not healthy:
        fail('Сайт возвращён, но не проходит проверку: %s\nПокажите это сообщение Claude.' % detail)
    ok('сайт возвращён к версии %s, как было до прерванного отката (%s)' % (src[:7], detail))
