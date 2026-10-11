#!/usr/bin/env python3
"""Состояние сайта kireevonline.ru — ТОЛЬКО ЧТЕНИЕ. Запускать могут Роман и Claude:

    cd ~/"Claude Code/kireevonline/gallery" && python3 deploy/status.py

Показывает: какая версия на сервере и на живом сайте, есть ли невыложенные
изменения на GitHub, ручные правки на сервере, фото/база/снимки, место на хостинге,
последние выкладки и откаты.
"""

import datetime

from readonly_gateway import GATE_VERSION
from server import ReadOnly, _get, fail, git, git_ok, ok, say, warn


def main():
    say('=== Состояние kireevonline.ru (только чтение) ===')
    ro = ReadOnly()
    if ro.fake:
        say('(ТЕСТОВЫЙ РЕЖИМ: «сервер» — папка %s)' % ro.fake)
    st = ro.call('state')
    if not st.get('ok'):
        fail('Не удалось прочитать сервер (%s):\n%s' % (st.get('step'), st.get('output')))
    info = ro.call('status')
    log = ro.call('readlog')

    head = st['head']
    say('')
    if git_ok('cat-file', '-e', head + '^{commit}'):
        say('Код на сервере:  ' + git('log', '-1', '--format=%h от %ad — %s', '--date=format:%d.%m.%Y %H:%M', head))
    else:
        say('Код на сервере:  %s (этой версии нет на Mac)' % head[:7])
    git('fetch', '--quiet', 'origin', check=False)
    gh = git('rev-parse', 'origin/main', check=False)
    if gh == head:
        ok('совпадает с GitHub')
    elif gh and git_ok('merge-base', '--is-ancestor', head, gh):
        n = git('rev-list', '--count', head + '..' + gh)
        warn('на GitHub есть невыложенные изменения: %s (выкладка: python3 deploy/deploy.py)' % n)
    else:
        warn('версия на сервере не совпадает с GitHub (%s)' % (gh[:7] if gh else '?'))
    if st['dirty']:
        warn('на сервере вручную изменены файлы: ' + ', '.join(st['dirty']))
    if st['origin_token']:
        warn('в настройках git на сервере ещё лежит старый токен (уберётся при следующей выкладке)')

    status, headers, _ = _get(ro.site + '/photos/')
    live = headers.get('x-site-version')
    if status != 200:
        warn('живой сайт ответил: %s' % status)
    elif live is None:
        say('Живой сайт:      открывается (метки версии пока нет — появится после первой выкладки)')
    elif live == head[:7]:
        ok('живой сайт открывается и работает на этой же версии')
    else:
        warn('живой сайт работает на версии %s — не на той, что лежит на сервере' % live)

    say('')
    mtime = datetime.datetime.fromtimestamp(st['db_mtime']).strftime('%d.%m.%Y %H:%M')
    say('База:            %d КБ, последнее изменение %s' % (st['db_size'] // 1024, mtime))
    if info.get('ok'):
        say('Фото:            %d файлов, %d МБ' % (info['media_files'], info['media_mb']))
        say('Снимков выкладок на сервере: %d' % len([s for s in info['snapshots'] if s.startswith('db_')]))
        for line in info.get('quota', []):
            say('Квота:           ' + line.strip())
    say('Python %s, Django %s' % (st['python'], st['django']))

    lines = log.get('lines', []) if log.get('ok') else []
    if lines:
        say('')
        say('Последние выкладки и откаты:')
        for line in lines[-5:]:
            f = line.split('\t')
            if len(f) >= 5:
                say('  %s  %-8s %s → %s  %s' % (f[0], f[1], f[2][:7], f[3][:7], f[4]))
    if st.get('gate_version', 0) < GATE_VERSION:
        warn('шлюз чтения на сервере устарел — Роман: python3 deploy/setup_readonly.py')


if __name__ == '__main__':
    main()
