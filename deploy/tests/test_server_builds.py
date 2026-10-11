"""Библиотеки из requirements.txt должны вставать на сервер: у хостинга старый Linux (glibc 2.17),
готовые сборки нужны в формате manylinux2014, собрать из исходников сервер не может
(09.10.2026 так не встал Pillow 12.3.0, выкладка вернулась сама). Нужен интернет (PyPI)."""

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'deploy'))

from server import check_server_wheels  # noqa: E402

SERVER_PYTHON = '3.13'


class ServerBuildsTests(unittest.TestCase):
    def test_every_library_has_a_build_for_the_server(self):
        try:
            subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            self.skipTest('нет git')
        fits, report = check_server_wheels('HEAD', SERVER_PYTHON)
        if not fits and ('Could not fetch' in report or 'NewConnectionError' in report):
            self.skipTest('нет доступа к PyPI')
        self.assertTrue(fits, report)


if __name__ == '__main__':
    unittest.main()
