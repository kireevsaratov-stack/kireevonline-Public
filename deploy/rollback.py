#!/usr/bin/env python3
"""Откат сайта kireevonline.ru на предыдущую версию. Запускает только Роман:

    cd ~/"Claude Code/kireevonline/gallery" && python3 deploy/rollback.py

Без параметров возвращает версию, которая стояла до последней выкладки.
    --to abc1234    вернуть конкретную версию (номер из журнала или git log)
    --restore-db    вернуть ещё и БАЗУ из снимка той выкладки (изменения в базе
                    после неё — новые фото, корзина — пропадут; файлы фото останутся)

Перед откатом делается снимок текущего состояния, так что откат тоже обратим.
Если менялась структура базы, она аккуратно возвращается миграциями (данные
сохраняются); если это невозможно — ничего не трогается и скрипт скажет, что делать.
"""

import argparse
import signal

from server import (
    Server,
    change_flags,
    changed_files,
    check_server,
    confirm,
    describe,
    fail,
    git,
    git_ok,
    has_version_marker,
    healthcheck,
    last_migration,
    now_stamp,
    ok,
    recover_interrupted_rollback,
    save_db_snapshot_to_mac,
    say,
    warn,
)

# Последний шаг базы, который записывает тексты и файлы (0009–0013). Откатывать за него обычным откатом нельзя.
LAST_CONTENT_MIGRATION = '0013_travel_lines'


def parse_log(lines):
    entries = []
    for line in lines:
        f = line.split('\t')
        if len(f) >= 7:
            entries.append(
                {'stamp': f[0], 'action': f[1], 'from': f[2], 'to': f[3], 'result': f[4], 'db': f[5], 'pip': f[6]}
            )
    return entries


def main():
    ap = argparse.ArgumentParser(description='Откат сайта kireevonline.ru')
    ap.add_argument('--to', help='версия, которую вернуть')
    ap.add_argument('--restore-db', action='store_true', help='вернуть и базу из снимка')
    args = ap.parse_args()

    say('=== Откат kireevonline.ru ===')
    srv = Server()
    if srv.fake:
        say('(ТЕСТОВЫЙ РЕЖИМ: «сервер» — папка %s)' % srv.fake)
    git('fetch', '--quiet', 'origin')
    st = check_server(srv)
    current = st['head']
    pending = st.get('pending')
    if pending and pending.get('kind') == 'rollback':
        recover_interrupted_rollback(srv, pending)  # сначала вернуть сайт к состоянию до прерванного отката
        say('Если откат всё ещё нужен — запустите его ещё раз.')
        return
    interrupted_deploy = bool(pending and pending.get('to') == current and pending.get('from') != current)

    log = srv.helper('readlog')
    entries = parse_log(log.get('lines', [])) if log.get('ok') else []
    last_deploy = next(
        (e for e in reversed(entries) if e['action'] == 'deploy' and e['result'] == 'OK' and e['to'] == current), None
    )

    if args.to:
        if not git_ok('cat-file', '-e', args.to + '^{commit}'):
            fail('Версия «%s» не найдена.' % args.to)
        target = git('rev-parse', args.to + '^{commit}')
    elif last_deploy:
        target = last_deploy['from']
    elif interrupted_deploy:  # прерванная выкладка: вернуть версию, с которой она началась
        target = pending['from']
    else:
        say('')
        say('Не нашёл в журнале выкладку, после которой стоит текущая версия %s.' % current[:7])
        if entries:
            say('Последние записи журнала:')
            for e in entries[-8:]:
                say('  %s  %s  %s → %s  %s' % (e['stamp'], e['action'], e['from'][:7], e['to'][:7], e['result']))
        fail('Укажите версию явно: python3 deploy/rollback.py --to <версия>')

    if target == current:
        say('На сайте уже версия %s. Откатывать нечего.' % current[:7])
        return
    if not git_ok('cat-file', '-e', current + '^{commit}'):
        fail('Версия на сервере (%s) неизвестна этому Mac. Ничего не трогаю.' % current[:7])

    files = changed_files(target, current)
    flags = change_flags(files)
    mig_cur, mig_target = last_migration(current), last_migration(target)
    migrate_to = ''
    db_restore = ''
    if args.restore_db:
        if not last_deploy or not last_deploy['db']:
            fail('Не знаю, из какого снимка возвращать базу. Ничего не трогаю.')
        if target != last_deploy['from']:
            # снимок сделан перед выкладкой last_deploy и соответствует версии last_deploy['from'];
            # вместе с другой версией кода база может не подойти по структуре
            fail(
                'Снимок базы есть только для версии %s, а выбрана %s. Ничего не трогаю.'
                % (last_deploy['from'][:7], target[:7])
            )
        db_restore = last_deploy['db']
    elif mig_cur != mig_target:
        if mig_target is None or mig_target > mig_cur:
            fail('Структура базы в версии %s новее текущей — это не откат. Ничего не трогаю.' % target[:7])
        if mig_target < LAST_CONTENT_MIGRATION <= mig_cur:
            # 0009–0013 не только меняют структуру, но и записывают тексты и файлы: их обратный ход вернёт
            # тексты альбомов «как было до шага», потеряв всё, что владелец написал после (аудит 2)
            fail(
                'Откат к версии %s отменил бы шаги базы с текстами альбомов (до %s) — тексты, написанные после, '
                'пропали бы. Обычным откатом так далеко назад нельзя. Покажите это сообщение Claude.'
                % (target[:7], LAST_CONTENT_MIGRATION)
            )
        migrate_to = mig_target

    say('')
    say('Сейчас на сайте:  %s' % describe(current))
    say('Вернётся версия:  %s' % describe(target))
    if git_ok('merge-base', '--is-ancestor', target, current):
        say('')
        say('Будут отменены изменения:')
        for subject in git('log', '--format=%s', target + '..' + current).splitlines():
            say('  • ' + subject)
    say('')
    if db_restore:
        warn('База будет возвращена из снимка %s.' % db_restore.rsplit('/', 1)[-1])
        warn('Всё, что менялось в базе после этого (новые фото, корзина), пропадёт из базы.')
    elif migrate_to:
        warn('Структура базы будет возвращена до %s (данные сохраняются).' % migrate_to)
    else:
        ok('База не меняется.')
    pip_file = ''
    if flags['reqs']:
        if last_deploy and last_deploy['pip'] and target == last_deploy['from']:
            pip_file = last_deploy['pip']
        else:
            pip_file = 'requirements.txt'
        warn('Будут возвращены библиотеки.')

    if not confirm('Откатить сайт на версию %s?' % target[:7]):
        say('Отменено. На сервере ничего не менялось.')
        return

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    say('')
    say('Не закрывайте окно до конца — идёт откат.')
    stamp = now_stamp()
    say('1/3 Снимок текущего состояния (чтобы откат тоже можно было отменить)…')
    snap = srv.helper('snapshot', stamp, 'before-rollback_' + current[:7])
    if not snap.get('ok'):
        fail('Снимок не сделан (%s):\n%s\nНичего не откатано.' % (snap.get('step'), snap.get('output')))
    local = save_db_snapshot_to_mac(srv, snap, '%s_before-rollback_%s' % (stamp, current[:7]))
    ok('снимок на сервере и копия базы на Mac: backups/db/%s' % local.name)
    # отметка «откат начат»: если его прервут, следующий запуск вернёт сайт к состоянию до него по этим снимкам
    marked = srv.helper('pending', current, target, snap['db'], snap['pip'] if snap.get('pip_ok') else '', 'rollback')
    if not marked.get('ok'):
        fail('Не удалось отметить начало отката на сервере:\n%s\nНичего не откатано.' % marked.get('output'))

    say('2/3 Откатываю и перезапускаю сайт…')
    back = srv.helper(
        'rollback', target, migrate_to, db_restore, pip_file, '1' if (flags['reqs'] or flags['static']) else '0', stamp
    )
    if not back.get('ok'):
        srv.log(stamp, 'rollback', current, target, 'FAILED_' + back.get('step', '?'), snap['db'], snap['pip'])
        if back.get('step') == 'reverse-migrate':
            restored = 'база возвращена из снимка' in (back.get('output') or '')
            state = (
                'База возвращена из снимка, сделанного прямо перед откатом; код не менялся — работает прежняя версия.'
                if restored
                else 'ВНИМАНИЕ: база могла остаться изменённой наполовину.'
            )
            fail(
                'Не удалось вернуть структуру базы миграциями:\n%s\n%s\n'
                'Покажите это сообщение Claude.' % (back.get('output'), state)
            )
        fail(
            'Откат не прошёл на шаге «%s»:\n%s\nПокажите это сообщение Claude.' % (back.get('step'), back.get('output'))
        )
    ok('готово: ' + ', '.join(back['done']))

    say('3/3 Проверяю живой сайт (обычно секунды; если хостинг медлит с перезапуском — до 6 минут)…')
    expect = target[:7] if has_version_marker(target) else None
    healthy, detail = healthcheck(srv.site, expect, nudge=lambda: srv.helper('restart'))
    srv.log(stamp, 'rollback', current, target, 'OK' if healthy else 'UNHEALTHY', snap['db'], snap['pip'])
    say('')
    if healthy:
        say('✔ ГОТОВО. На сайте версия %s. %s.' % (target[:7], detail.capitalize()))
        say('  Вернуть отменённую версию: python3 deploy/deploy.py')
    else:
        say('✖ Откат выполнен, но сайт не проходит проверку: %s' % detail)
        say('  Покажите это сообщение Claude.')
        raise SystemExit(3)


if __name__ == '__main__':
    main()
