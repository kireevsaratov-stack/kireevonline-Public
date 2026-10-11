#!/usr/bin/env python3
"""Выкладка сайта kireevonline.ru. Запускает только Роман:

    cd ~/"Claude Code/kireevonline/gallery" && python3 deploy/deploy.py

Выкладывает ровно то, что лежит на GitHub (ветка main). Порядок:
1. проверка сервера (только чтение) и показ, что изменится;
   автотесты на выкладываемой версии — не прошли, значит выкладки не будет;
2. ваше «да»;
3. снимок базы и списка библиотек на сервере + копия базы на Mac;
4. выкладка кода, при необходимости миграции/библиотеки/статика, перезапуск;
5. проверка живого сайта; если он не открылся — автоматический возврат
   предыдущей версии (и базы из снимка, если менялась её структура).
"""

import os
import signal

from server import (
    Server,
    change_flags,
    changed_files,
    check_server,
    check_server_wheels,
    confirm,
    describe,
    fail,
    git,
    git_ok,
    has_version_marker,
    healthcheck,
    now_stamp,
    ok,
    recover_interrupted_rollback,
    run_tests_at,
    save_db_snapshot_to_mac,
    say,
    warn,
)


def main():
    say('=== Выкладка kireevonline.ru ===')
    srv = Server()
    if srv.fake:
        say('(ТЕСТОВЫЙ РЕЖИМ: «сервер» — папка %s)' % srv.fake)

    git('fetch', '--quiet', 'origin')
    target = git('rev-parse', 'origin/main')
    ahead = git('rev-list', '--count', 'origin/main..HEAD')
    if ahead != '0':
        warn('На Mac есть %s сохранённых изменений, которых нет на GitHub — они НЕ будут выложены.' % ahead)

    st = check_server(srv)
    current = st['head']
    pending = st.get('pending')
    if pending and pending.get('kind') == 'rollback':
        recover_interrupted_rollback(srv, pending)  # сначала вернуть сайт к состоянию до прерванного отката
        say('Запустите выкладку ещё раз.')
        return
    resume = bool(pending and pending.get('to') == current and pending.get('from') != current)
    if resume:
        # прошлая выкладка прервалась после смены кода: на сервере новый код, а библиотеки, база, стили
        # или проверка могли не дойти — выкладываем заново от последней завершённой версии
        warn('Прошлая выкладка %s → %s не была завершена — доделаю её.' % (pending['from'][:7], pending['to'][:7]))
        current = pending['from']
    if current == target:
        say('')
        say('На сайте уже эта версия: %s' % describe(target))
        say('Выкладывать нечего.')
        return
    if not git_ok('cat-file', '-e', current + '^{commit}'):
        fail('Версия на сервере (%s) неизвестна этому Mac. Ничего не трогаю.' % current[:7])
    if not git_ok('merge-base', '--is-ancestor', current, target):
        fail(
            'Версия на GitHub не продолжает версию на сервере (%s). Ничего не трогаю.\n'
            'Покажите это сообщение Claude.' % current[:7]
        )

    files = changed_files(current, target)
    flags = change_flags(files)
    say('')
    say('Сейчас на сайте:  %s' % describe(current))
    say('Будет выложено:   %s' % describe(target))
    say('')
    say('Изменения:')
    for subject in git('log', '--reverse', '--format=%s', current + '..' + target).splitlines():
        say('  • ' + subject)
    say('')
    say('Файлов изменено: %d' % len(files))
    if flags['migr']:
        warn('Меняется СТРУКТУРА БАЗЫ (миграции). Перед этим будет снимок базы.')
    if flags['reqs']:
        warn('Меняется список библиотек (requirements.txt) — на сервере будет pip install.')
    if not (flags['migr'] or flags['reqs']):
        ok('База и библиотеки не меняются — только код и шаблоны.')
    if st['origin_token']:
        say('  • Заодно из настроек git на сервере будет убран старый токен GitHub.')

    if flags['reqs']:
        say('')
        say('Проверяю, что новые библиотеки встанут на сервер…')
        fits, report = check_server_wheels(target, st['python'])
        if not fits:
            fail(
                'Не для всех библиотек есть сборки под сервер — выкладка их бы не поставила. Сайт не менялся.\n%s\n'
                'Покажите это сообщение Claude.' % report
            )
        ok(report)

    say('')
    say('Проверяю автотесты на этой версии (около полуминуты)…')
    if srv.fake and os.environ.get('KO_FAKE_SKIP_TESTS'):  # только тест автовозврата на копии сервера
        passed, report = True, 'автотесты пропущены (тестовый режим)'
    else:
        passed, report = run_tests_at(target)
    if not passed:
        fail(
            'Автотесты на версии %s не прошли — выкладывать её нельзя. Сайт не менялся.\n%s\n'
            'Покажите это сообщение Claude.' % (target[:7], report)
        )
    ok(report)

    if not confirm('Выложить эту версию на kireevonline.ru?'):
        say('Отменено. На сервере ничего не менялось.')
        return

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    say('')
    say('Не закрывайте окно до конца — идёт выкладка.')
    stamp = now_stamp()
    short_cur, short_new = current[:7], target[:7]

    say('1/4 Снимок перед выкладкой…')
    snap = srv.helper('snapshot', stamp, 'before_' + short_new)
    if not snap.get('ok'):
        fail('Снимок не сделан (%s):\n%s\nНичего не выложено.' % (snap.get('step'), snap.get('output')))
    ok('снимок базы на сервере: %s (%d КБ)' % (snap['db'].rsplit('/', 1)[-1], snap['db_size'] // 1024))
    if 'token-removed' in snap['notes']:
        ok('старый токен GitHub убран из настроек git на сервере')
    local = save_db_snapshot_to_mac(srv, snap, '%s_before-deploy_%s' % (stamp, short_new))
    ok('копия базы на Mac: backups/db/%s' % local.name)
    if flags['reqs'] and not snap.get('pip_ok'):
        fail('Не удалось записать список библиотек на сервере — обновлять их без снимка нельзя. Ничего не выложено.')
    # снимок «до» для автовозврата: при доделке прерванной выкладки — снимок, сделанный ДО неё
    restore_db = (pending.get('db') or snap['db']) if resume else snap['db']
    this_pip = snap['pip'] if snap.get('pip_ok') else ''
    restore_pip = (pending.get('pip') or this_pip) if resume else this_pip
    marked = srv.helper('pending', current, target, restore_db, restore_pip, 'deploy')
    if not marked.get('ok'):
        fail('Не удалось отметить начало выкладки на сервере:\n%s\nНичего не выложено.' % marked.get('output'))

    say('2/4 Передаю код на сервер…')
    pushed, detail = srv.push(target)
    if not pushed:
        srv.log(stamp, 'deploy', current, target, 'PUSH_FAILED', snap['db'], snap['pip'], '', '', '')
        fail('Не удалось передать код на сервер:\n%s\nСайт не менялся.' % detail)
    ok('код передан')

    say('3/4 Применяю и перезапускаю сайт…')
    fl = ['1' if flags[k] else '0' for k in ('reqs', 'migr', 'static')]
    applied = srv.helper('apply', target, *fl)
    healthy, detail = False, ''
    if applied.get('ok'):
        ok('готово: ' + ', '.join(applied['done']))
        say('4/4 Проверяю живой сайт (обычно секунды; если хостинг медлит с перезапуском — до 6 минут)…')
        expect = short_new if has_version_marker(target) else None
        healthy, detail = healthcheck(srv.site, expect, nudge=lambda: srv.helper('restart'))
    else:
        detail = 'шаг «%s» не прошёл:\n%s' % (applied.get('step'), applied.get('output'))

    if healthy:
        srv.log(stamp, 'deploy', current, target, 'OK', snap['db'], snap['pip'], *fl)
        say('')
        say('✔ ГОТОВО. На сайте версия %s. %s.' % (short_new, detail.capitalize()))
        say('  Если что-то не так — откат одной командой: python3 deploy/rollback.py')
        return

    say('')
    say('✖ Сайт после выкладки не прошёл проверку: %s' % detail)
    say('  Автоматически возвращаю предыдущую версию %s…' % short_cur)
    back = srv.helper(
        'rollback',
        current,
        '',
        restore_db if flags['migr'] else '',
        restore_pip if flags['reqs'] else '',
        '1' if (flags['reqs'] or flags['static']) else '0',
        stamp,
    )
    if not back.get('ok'):
        srv.log(stamp, 'deploy', current, target, 'AUTO_ROLLBACK_FAILED', snap['db'], snap['pip'], *fl)
        fail(
            'ВНИМАНИЕ: автоматический возврат не удался (%s):\n%s\n'
            'Снимок базы: %s. Покажите это сообщение Claude.' % (back.get('step'), back.get('output'), snap['db'])
        )
    expect = short_cur if has_version_marker(current) else None
    healthy, detail2 = healthcheck(srv.site, expect, nudge=lambda: srv.helper('restart'))
    srv.log(
        stamp,
        'deploy',
        current,
        target,
        'AUTO_ROLLED_BACK' if healthy else 'AUTO_ROLLBACK_UNHEALTHY',
        snap['db'],
        snap['pip'],
        *fl,
    )
    if healthy:
        say('✔ Предыдущая версия %s возвращена, сайт работает (%s).' % (short_cur, detail2))
        say('  Новая версия НЕ выложена. Покажите это сообщение Claude — разберёмся.')
        sys_exit_code = 2
    else:
        say('✖ Предыдущая версия возвращена, но сайт всё ещё не проходит проверку: %s' % detail2)
        say('  Покажите это сообщение Claude.')
        sys_exit_code = 3
    raise SystemExit(sys_exit_code)


if __name__ == '__main__':
    main()
