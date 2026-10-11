"""Версия кода (коммит git), на которой запущен сайт.

Читается из .git один раз при старте процесса и отдаётся в заголовке
X-Site-Version каждого ответа. По нему deploy/deploy.py проверяет, что сайт
действительно перезапустился на новом коде, а версию на живом сайте можно
узнать без входа на сервер: curl -sI https://kireevonline.ru/photos/
"""

from pathlib import Path

_GIT = Path(__file__).resolve().parent.parent / '.git'


def _read_version():
    try:
        head = (_GIT / 'HEAD').read_text().strip()
        if not head.startswith('ref: '):
            return head[:7]
        ref = head[5:]
        ref_file = _GIT / ref
        if ref_file.exists():
            return ref_file.read_text().strip()[:7]
        packed = _GIT / 'packed-refs'
        if packed.exists():
            for line in packed.read_text().splitlines():
                if line.endswith(' ' + ref):
                    return line[:7]
    except OSError:
        pass
    return 'unknown'


VERSION = _read_version()


class VersionHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Site-Version'] = VERSION
        return response
