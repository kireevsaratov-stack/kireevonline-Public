"""Выкладка, откат и автовозврат — по-настоящему, на копии сервера во временной папке Mac (сеть не нужна).

Как устроено: проверяемый код кладётся во временный «GitHub» (голый git-репозиторий), из него — рабочая копия
(откуда запускаются deploy/deploy.py и deploy/rollback.py) и «сервер» (папка с domains/kireevonline.ru/...),
на котором работает сайт (manage.py runserver). Скрипты запускаются в тестовом режиме KO_FAKE_SERVER и
ходят только в эту папку. Настоящий сервер не участвует.

Запуск: python3 -m unittest deploy/tests/test_deploy_fake.py   (около 3 минут)
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = Path(os.environ.get('KO_TEST_PY') or REPO.parent / '.venv' / 'bin' / 'python')
MARK = 'Проверка выкладки 7f3a'


def sh(*args, cwd=None, **kw):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True, **kw).stdout.strip()


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


SEED = """
import io
from django.core.files.base import ContentFile
from PIL import Image
from photos.models import Album, Photo, Section
s = Section.objects.create(name='Путешествия', slug='puteshestviya')
a = Album.objects.create(section=s, name='Бали')
buf = io.BytesIO(); Image.new('RGB', (64, 48), 'gray').save(buf, 'JPEG')
p = Photo(section=s, album=a, title='kadr'); p.image.save('kadr.jpg', ContentFile(buf.getvalue()))
"""


@unittest.skipUnless(PY.exists(), 'нет Python с Django: %s' % PY)
class FakeServerDeployTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='kireevonline-fake-'))
        self.origin = self.tmp / 'origin.git'
        self.work = self.tmp / 'work' / 'gallery'
        self.server = self.tmp / 'server'
        self.app = self.server / 'domains' / 'kireevonline.ru' / 'gallery'
        public = self.server / 'domains' / 'kireevonline.ru' / 'public_html'

        # «GitHub» с проверяемой версией в main
        head = sh('git', 'rev-parse', 'HEAD', cwd=REPO)
        sh(
            'git', 'init', '--bare', '--quiet', '--initial-branch=main', str(self.origin)
        )  # имя ветки — явно: на разных машинах по умолчанию master или main
        sh('git', 'push', '--quiet', str(self.origin), '%s:refs/heads/main' % head, cwd=REPO)
        sh('git', 'clone', '--quiet', str(self.origin), str(self.work))
        for k, v in (('user.name', 'Test'), ('user.email', 'test@example.com')):
            sh('git', 'config', k, v, cwd=self.work)
        self.v1 = sh('git', 'rev-parse', 'HEAD', cwd=self.work)

        # «сервер»: код той же версии, своя база с одним альбомом, site.wsgi и media
        sh('git', 'clone', '--quiet', str(self.origin), str(self.app))
        (public / 'media').mkdir(parents=True)
        (public / 'site.wsgi').write_text('# заглушка\n')
        env = self._site_env()
        sh(str(PY), 'manage.py', 'migrate', '--noinput', cwd=self.app, env=env)
        sh(str(PY), 'manage.py', 'shell', '-c', SEED, cwd=self.app, env=env)

        self.port = free_port()
        self.site = 'http://127.0.0.1:%d' % self.port
        self.runserver = subprocess.Popen(
            [str(PY), 'manage.py', 'runserver', '127.0.0.1:%d' % self.port],
            cwd=self.app,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_site()

    def tearDown(self):
        self.runserver.terminate()
        self.runserver.wait(timeout=20)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- помощники ----

    def _site_env(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(('KO_', 'DJANGO_'))}
        env['DJANGO_DEBUG'] = 'True'
        return env

    def _wait_site(self, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                urllib.request.urlopen(self.site + '/', timeout=5)
                return
            except Exception:
                time.sleep(0.5)
        self.fail('сайт на копии сервера не поднялся')

    def _run(self, script, *args, skip_tests=False):
        env = self._site_env()
        env.pop('DJANGO_DEBUG')
        env.update(
            KO_FAKE_SERVER=str(self.server),
            KO_FAKE_PY=str(PY),
            KO_SITE_URL=self.site,
            KO_FAKE_RESTART_FILE='config/urls.py',
            KO_TEST_PY=str(PY),
            KO_FAKE_HEALTH_TIMEOUT='45',
        )
        if skip_tests:
            env['KO_FAKE_SKIP_TESTS'] = '1'
        assert env['KO_FAKE_SERVER'].startswith(str(self.tmp))  # только копия сервера
        return subprocess.run(
            [sys.executable, str(self.work / 'deploy' / script), *args],
            cwd=self.work,
            env=env,
            input='да\n',
            capture_output=True,
            text=True,
            timeout=900,
        )

    def _commit(self, path, old, new, message):
        f = self.work / path
        f.write_text(f.read_text(encoding='utf-8').replace(old, new, 1), encoding='utf-8')
        sh('git', 'commit', '--quiet', '-am', message, cwd=self.work)
        sh('git', 'push', '--quiet', 'origin', 'HEAD:main', cwd=self.work)
        return sh('git', 'rev-parse', 'HEAD', cwd=self.work)

    def _server_head(self):
        return sh('git', 'rev-parse', 'HEAD', cwd=self.app)

    def _about(self):
        self._wait_site()
        return urllib.request.urlopen(self.site + '/about/', timeout=10).read().decode()

    # ---- проверки ----

    def test_deploy_then_rollback(self):
        v2 = self._commit(
            'photos/templates/photos/about.html',
            '<h1>Обо мне</h1>',
            '<h1>Обо мне</h1><p>%s</p>' % MARK,
            'тестовая правка',
        )
        r = self._run('deploy.py')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('ГОТОВО', r.stdout)
        self.assertEqual(self._server_head(), v2)
        self.assertIn(MARK, self._about())
        self.assertTrue(list((self.work.parent / 'backups' / 'db').glob('db_*_before-deploy_*.sqlite3')))

        r = self._run('rollback.py')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._server_head(), self.v1)
        self.assertNotIn(MARK, self._about())

    def test_version_with_failing_tests_is_not_deployed(self):
        self._commit(
            'photos/views/pages.py',
            "return render(request, 'photos/about.html')",
            "return render(request, 'photos/no-such-template.html')",
            'сломанная страница «Обо мне»',
        )
        r = self._run('deploy.py')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Автотесты', r.stdout + r.stderr)
        self.assertEqual(self._server_head(), self.v1)

    def test_broken_site_is_rolled_back_automatically(self):
        self._commit(
            'photos/views/pages.py',
            "return render(request, 'photos/about.html')",
            "return render(request, 'photos/no-such-template.html')",
            'сломанная страница «Обо мне»',
        )
        self._commit('photos/views/seo.py', "'Allow: /',", "'Allow: /', 1 / 0,", 'сломанный robots.txt')
        r = self._run('deploy.py', skip_tests=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('Предыдущая версия', r.stdout)
        self.assertEqual(self._server_head(), self.v1)

    # ---- сценарии из внешнего аудита 09.10.2026 ----

    def _add_file(self, path, text, message):
        f = self.work / path
        f.write_text(text, encoding='utf-8')
        sh('git', 'add', path, cwd=self.work)
        sh('git', 'commit', '--quiet', '-m', message, cwd=self.work)
        sh('git', 'push', '--quiet', 'origin', 'HEAD:main', cwd=self.work)
        return sh('git', 'rev-parse', 'HEAD', cwd=self.work)

    def _snapdir(self):
        return self.server / 'deploy-backups'

    def test_interrupted_deploy_is_finished_by_next_run(self):
        """Код уже сменился, а выкладка не дошла до конца — повтор не говорит «нечего выкладывать», а доделывает."""
        import json

        v2 = self._commit('photos/templates/photos/about.html', '<h1>Обо мне</h1>',
                          '<h1>Обо мне</h1><p>%s</p>' % MARK, 'тестовая правка')  # fmt: skip
        self._snapdir().mkdir(exist_ok=True)
        (self._snapdir() / 'pending-deploy.json').write_text(json.dumps({'from': self.v1, 'to': v2, 'db': ''}))
        sh('git', 'fetch', '--quiet', 'origin', cwd=self.app)
        sh('git', 'reset', '--quiet', '--hard', v2, cwd=self.app)  # «обрыв» сразу после смены кода
        r = self._run('deploy.py', skip_tests=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('не была завершена', r.stdout)
        self.assertIn('ГОТОВО', r.stdout)
        self.assertFalse((self._snapdir() / 'pending-deploy.json').exists())
        self.assertIn(MARK, self._about())

    def test_failed_reverse_migration_restores_database(self):
        """Откат миграцией сорвался — база возвращается из снимка, а не остаётся «наполовину»."""
        last = sorted(p.stem for p in (self.work / 'photos' / 'migrations').glob('[0-9][0-9][0-9][0-9]_*.py'))[-1]
        migration = (
            'from django.db import migrations, models\n\n\n'
            'def forward(apps, schema_editor):\n    pass\n\n\n'
            'def backward(apps, schema_editor):\n    raise RuntimeError("обратный шаг сломан")\n\n\n'
            'class Migration(migrations.Migration):\n'
            '    dependencies = [("photos", "LAST")]\n'
            '    operations = [\n'
            '        migrations.AddField("album", "audit_probe", models.IntegerField(default=0)),\n'
            '        migrations.RunPython(forward, backward),\n'
            '    ]\n'
        ).replace('LAST', last)
        probe = 'photos/migrations/%04d_audit_probe.py' % (int(last[:4]) + 1)
        self._add_file(probe, migration, 'миграция со сломанным откатом')
        r = self._run('deploy.py', skip_tests=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        db = self.app / 'db.sqlite3'
        cols = sh('sqlite3', str(db), 'SELECT name FROM pragma_table_info("photos_album")')
        self.assertIn('audit_probe', cols)
        r = self._run('rollback.py')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('База возвращена из снимка', r.stdout + r.stderr)
        cols = sh('sqlite3', str(db), 'SELECT name FROM pragma_table_info("photos_album")')
        self.assertIn('audit_probe', cols)  # база цела, как до попытки отката
        applied = sh('sqlite3', str(db), "SELECT count(*) FROM django_migrations WHERE name LIKE '%_audit_probe'")
        self.assertEqual(applied, '1')

    def test_restore_db_only_with_its_own_version(self):
        v2 = self._commit('photos/templates/photos/about.html', '<h1>Обо мне</h1>', '<h1>Обо мне</h1><p>2</p>', 'v2')
        self.assertEqual(self._run('deploy.py', skip_tests=True).returncode, 0)
        self._commit('photos/templates/photos/about.html', '<p>2</p>', '<p>3</p>', 'v3')
        self.assertEqual(self._run('deploy.py', skip_tests=True).returncode, 0)
        r = self._run('rollback.py', '--to', self.v1, '--restore-db')  # снимок последней выкладки — от v2
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Снимок базы есть только для версии', r.stdout + r.stderr)
        self.assertNotEqual(self._server_head(), self.v1)
        self.assertNotEqual(v2, self.v1)

    def test_interrupted_rollback_is_undone_by_next_run(self):
        """Аудит 2: откат прервали посреди — база изменена, код прежний. Следующий запуск возвращает всё как было."""
        import json
        import shutil as sh_

        v2 = self._commit('photos/templates/photos/about.html', '<h1>Обо мне</h1>', '<h1>Обо мне</h1><p>v2</p>', 'v2')
        self.assertEqual(self._run('deploy.py', skip_tests=True).returncode, 0)
        db = self.app / 'db.sqlite3'
        snapdir = self._snapdir()
        before = snapdir / 'db_before-interrupted-rollback.sqlite3'
        sh_.copy(db, before)  # снимок «до отката», как его делает rollback.py
        (snapdir / 'pending-deploy.json').write_text(
            json.dumps({'from': v2, 'to': self.v1, 'db': str(before), 'pip': '', 'kind': 'rollback'})
        )
        sh(
            'sqlite3',
            str(db),
            "INSERT INTO photos_section (name, slug, \"order\", hidden) VALUES ('Обрыв', 'obryv', 99, 0)",
        )
        r = self._run('deploy.py', skip_tests=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('был прерван', r.stdout)
        self.assertEqual(sh('sqlite3', str(db), "SELECT count(*) FROM photos_section WHERE slug='obryv'"), '0')
        self.assertEqual(self._server_head(), v2)
        self.assertFalse((snapdir / 'pending-deploy.json').exists())

    def test_rollback_across_text_migrations_is_refused(self):
        """Аудит 2: откат за шаги 0009–0013 стёр бы тексты альбомов — обычным откатом нельзя."""
        # версия, где последний шаг базы — 0012; собирается здесь же, чтобы тест не зависел от истории git
        # (в публичной копии проекта истории нет)
        sh('git', 'switch', '--quiet', '-c', 'before-0013', cwd=self.work)
        later = sorted(p.name for p in (self.work / 'photos' / 'migrations').glob('0*.py') if p.name > '0013')
        sh('git', 'rm', '--quiet', *('photos/migrations/' + n for n in later), cwd=self.work)
        sh('git', 'commit', '--quiet', '-m', 'версия до шага 0013', cwd=self.work)
        old = sh('git', 'rev-parse', 'HEAD', cwd=self.work)
        sh('git', 'switch', '--quiet', 'main', cwd=self.work)
        r = self._run('rollback.py', '--to', old)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('тексты, написанные после', r.stdout + r.stderr)
        self.assertEqual(self._server_head(), self.v1)


class ChangeFlagsTests(unittest.TestCase):
    def test_new_libraries_also_rebuild_static(self):
        sys.path.insert(0, str(REPO / 'deploy'))
        from server import change_flags

        self.assertTrue(change_flags(['requirements.txt'])['static'])
        self.assertFalse(change_flags(['photos/views/pages.py'])['static'])


if __name__ == '__main__':
    unittest.main()
