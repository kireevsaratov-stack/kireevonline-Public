#!/usr/bin/env python3
"""Разовая настройка доступа ТОЛЬКО ДЛЯ ЧТЕНИЯ для Claude. Запускает только Роман:

    cd ~/"Claude Code/kireevonline/gallery" && python3 deploy/setup_readonly.py

Что делает на сервере:
1. кладёт шлюз ~/ro-gate.py (копия deploy/readonly_gateway.py) — он умеет только читать;
2. добавляет в ~/.ssh/authorized_keys одну строку: ключ Claude с ограничением
   «по этому ключу — только шлюз» (перед этим делает копию файла; ваш ключ
   и остальные строки не трогаются);
3. проверяет, что ваш ключ работает, чтение по ключу Claude работает, а любая
   посторонняя команда по ключу Claude сервером отклоняется. Если хостинг не
   соблюдает ограничение — ключ Claude тут же удаляется с сервера.
Повторный запуск безопасен (обновляет шлюз и строку ключа).
"""

import base64

from server import REPO, RO_COMMENT, RO_KEY, ReadOnly, Server, confirm, fail, ok, say


def main():
    say('=== Доступ только для чтения для Claude ===')
    pub_file = RO_KEY.parent / (RO_KEY.name + '.pub')
    if not RO_KEY.exists() or not pub_file.exists():
        fail('Нет ключа %s — попросите Claude его создать.' % RO_KEY)
    pub = pub_file.read_text().strip()
    if not pub.endswith(RO_COMMENT):
        fail('Ключ %s не похож на ключ Claude (нет подписи %s).' % (pub_file, RO_COMMENT))
    srv = Server()
    if srv.fake:
        say('(ТЕСТОВЫЙ РЕЖИМ: «сервер» — папка %s)' % srv.fake)
    probe = srv.helper('readlog')
    if not probe.get('ok'):
        fail('Нет связи с сервером по вашему ключу:\n%s' % probe.get('output'))

    say('')
    say('На сервере будет:')
    say('  • файл ~/ro-gate.py — шлюз, который умеет только читать;')
    say('  • одна новая строка в ~/.ssh/authorized_keys — ключ Claude с ограничением')
    say('    «только шлюз». Ваш ключ и остальные строки не меняются, копия файла сохраняется.')
    if not confirm('Настроить доступ только для чтения?'):
        say('Отменено. На сервере ничего не менялось.')
        return

    gate = base64.b64encode((REPO / 'deploy' / 'readonly_gateway.py').read_bytes()).decode()
    res = srv.helper('install_gate', gate, pub, RO_COMMENT)
    if not res.get('ok'):
        fail('Не получилось (%s):\n%s' % (res.get('step'), res.get('output')))
    ok('шлюз и ключ установлены (копия прежнего authorized_keys: %s)' % (res['backup'] or 'файла не было'))

    def undo(reason):
        back = srv.helper('uninstall_gate', RO_COMMENT)
        state = 'ключ Claude удалён с сервера' if back.get('ok') else 'НЕ УДАЛОСЬ удалить ключ Claude!'
        fail('%s\n%s. Покажите это сообщение Claude.' % (reason, state))

    say('Проверки:')
    if not srv.helper('readlog').get('ok'):
        fail(
            'ВНИМАНИЕ: ваш основной ключ перестал работать. Копия файла ключей: %s. '
            'Покажите это сообщение Claude.' % res['backup']
        )
    ok('ваш ключ работает как раньше')

    ro = ReadOnly()
    st = ro.call('state')
    if not st.get('ok'):
        undo('Чтение по ключу Claude не заработало:\n%s' % st.get('output'))
    ok('чтение по ключу Claude работает (версия на сервере %s)' % st['head'][:7])

    marker = b'KO_GATE_PROBE_' + b'MUST_NOT_RUN'
    code, out, err = ro.raw('echo ' + marker.decode())
    if marker in out:
        undo('ОПАСНО: сервер выполнил постороннюю команду по ключу Claude — ограничение не работает.')
    code2, out2, _ = ro.raw('touch ro-gate-write-test')
    if code == 0 or code2 == 0:
        undo('Шлюз не отклонил постороннюю команду.')
    ok('посторонние команды по ключу Claude отклоняются сервером')

    say('')
    say('✔ ГОТОВО. Claude может читать сервер (состояние, журнал, бэкапы),')
    say('  но не может ничего на нём изменить.')


if __name__ == '__main__':
    main()
