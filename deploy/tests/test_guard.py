"""Проверка блокировки сервера для AI-помощника: ~/.claude/hooks/kireevonline-guard.sh.

Сама блокировка лежит вне проекта (в настройках Claude Code на Mac), чтобы помощник не мог её ослабить
правкой кода; здесь только проверка, что она делает своё дело. На машине без блокировки (например, в
автопроверке на GitHub) тесты пропускаются.

Запуск: python3 -m unittest deploy/tests/test_guard.py
"""

import json
import subprocess
import unittest
from pathlib import Path

GUARD = Path.home() / '.claude' / 'hooks' / 'kireevonline-guard.sh'

BLOCKED = [
    'python3 deploy/deploy.py',
    'cd ~/"Claude Code/kireevonline/gallery" && python3 deploy/deploy.py',
    'python3 deploy/rollback.py --to 1e2b7ec',
    'python3 deploy/setup_readonly.py',
    'python3 tools/deploy.py',  # старый путь тоже
    'bash -c "python3 deploy/deploy.py"',
    'ssh user@kireevonline.ru ls',
    'scp db.sqlite3 kireevonline.ru:/home/user/',
    'rsync -a media/ kireevonline.ru:media/',
    'curl -X POST https://kireevonline.ru/admin/login/',
    'curl -d "a=1" https://kireevonline.ru/',
    'KO_FAKE_SERVER=/tmp/x python3 deploy/deploy.py && python3 deploy/deploy.py',  # второй запуск — настоящий
    # история на GitHub: перезаписать или удалить нельзя (решение Романа 12.10.2026)
    'git push --force origin main',
    'git push -f origin main',
    'git push --force-with-lease origin main',
    'cd "../public repo" && git push origin +main',
    'git -C ../public-repo push origin --delete main',
    'git push origin :main',
    'git push --mirror origin',
]

ALLOWED = [
    'python3 deploy/status.py',
    'python3 deploy/backup.py --db-only',
    'cat deploy/deploy.py',
    'grep -n healthcheck deploy/deploy.py',
    'curl -s https://kireevonline.ru/robots.txt',
    'KO_FAKE_SERVER=/tmp/fake KO_FAKE_PY=/tmp/py KO_SITE_URL=http://127.0.0.1:8200 python3 deploy/deploy.py',
    'git push origin main',
    'git push -q origin main 2>&1 | tail -2',
    'git push -u origin main && git log --oneline -1',
    'git push origin tests-cleanup:main',
    'git push origin main && rm -f x.png',
]


def run_guard(command):
    payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': command}})
    return subprocess.run(['bash', str(GUARD)], input=payload, capture_output=True, text=True).returncode


@unittest.skipUnless(GUARD.exists(), 'блокировки нет на этой машине')
class GuardTests(unittest.TestCase):
    def test_blocks_server_changes(self):
        for command in BLOCKED:
            with self.subTest(command=command):
                self.assertEqual(run_guard(command), 2)

    def test_allows_reading_and_tests(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertEqual(run_guard(command), 0)


if __name__ == '__main__':
    unittest.main()
