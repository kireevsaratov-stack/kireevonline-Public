#!/bin/bash
# Копия для чтения. Рабочая лежит вне проекта — ~/.claude/hooks/kireevonline-guard.sh —
# и подключена в Claude Code как хук PreToolUse: каждая команда Claude сначала проходит через неё.
# Проверка блокировки — deploy/tests/test_guard.py. Имя пользователя и адреса сервера заменены.
# Защита сайта kireevonline.ru (решение Романа, 29.09.2026):
# Claude читает сервер ТОЛЬКО через шлюз чтения (tools/status.py, tools/backup.py) и НЕ меняет сервер.
# Выкладку, откат и настройку сервера делает только Роман сам, командами из README сайта.
# Хук PreToolUse: exit 2 = команда отклонена, сообщение уходит Claude.

input=$(cat)
cmd=$(printf '%s' "$input" | /usr/bin/jq -r '(.tool_input.command // .tool_input.cmd // (.tool_input | tostring))' 2>/dev/null)
[ -z "$cmd" ] && cmd="$input"

hosts='(kireevonline\.ru|<адрес-сервера>|<адрес-сервера-2>|xsph\.ru)'

block() {
  echo "ЗАБЛОКИРОВАНО защитой сайта kireevonline: $1. Claude читает сервер только через python3 tools/status.py и tools/backup.py (шлюз только-для-чтения). Выкладку, откат и настройку сервера делает только Роман сам (см. README сайта). Не обходить: подготовь команду и отдай её Роману." >&2
  exit 2
}

# 1. Сетевые инструменты, направленные на сервер сайта
printf '%s' "$cmd" | grep -Eiq "(ssh|scp|sftp|rsync|sshfs|mosh|telnet|lftp)[^|;&]*$hosts" && block "подключение к серверу"

# 2. Вход под пользователем хостинга
printf '%s' "$cmd" | grep -Eq 'user@' && block "вход на сервер под пользователем хостинга"

# 3. ЗАПУСК скриптов, меняющих сервер (выкладка, откат, установка шлюза) —
#    только в тестовом режиме на Mac. Читать/проверять эти файлы можно.
#    status.py и backup.py разрешены: они ходят только через шлюз чтения ro-gate.py,
#    и запись по ключу Claude запрещает сам сервер.
#    Тестовый режим засчитывается, только если KO_FAKE_SERVER=<непустая папка>
#    стоит прямо перед этим же запуском (каждым, если их несколько).
script="(['\"][^'\"]*|(\\\\ |[^[:space:]])*)(tools|deploy)/(deploy|rollback|setup_readonly)\.py"
interp="(python[0-9.]*|pypy[0-9.]*|bash|sh|zsh)"
flags="([[:space:]]+-[A-Za-z0-9=]+)*"
any_run="${interp}${flags}[[:space:]]+${script}|(^|[;&|(]|&&|\|\|)[[:space:]]*${script}"
fake_run="KO_FAKE_SERVER=[^[:space:];&|'\"]+([[:space:]]+[A-Z_]+=[^[:space:];&|]*)*[[:space:]]+[^[:space:];&|]*${interp}${flags}[[:space:]]+${script}"
n_any=$(printf '%s\n' "$cmd" | grep -Eo "$any_run" | wc -l)
n_fake=$(printf '%s\n' "$cmd" | grep -Eo "$fake_run" | wc -l)
if [ "$n_any" -gt "$n_fake" ]; then
  # Разовое разрешение: файл «<срок unix> <скрипт> [<скрипт>…]». Создаётся ТОЛЬКО по явному
  # «да» Романа в чате на конкретные действия и удаляется сразу после них.
  allow="$HOME/.claude/hooks/kireevonline-allow-once"
  permitted=0
  if [ -f "$allow" ]; then
    read -r expiry names < "$allow"
    if [ "$(date +%s)" -lt "${expiry:-0}" ] 2>/dev/null; then
      permitted=1
      for s in $(printf '%s\n' "$cmd" | grep -Eo '(tools|deploy)/(deploy|rollback|setup_readonly)\.py' | sed -E 's#(tools|deploy)/##; s#\.py##' | sort -u); do
        case " $names " in *" $s "*) ;; *) permitted=0 ;; esac
      done
    fi
  fi
  [ "$permitted" -eq 1 ] || block "запуск скрипта выкладки/отката/настройки сервера"
fi

# 5. История на GitHub (решение Романа, 12.10.2026): отправлять новые версии можно, перезаписывать
#    и удалять — нет. Второй замок к правилу «main» на GitHub (запрет удаления и force push).
for seg in $(printf '%s\n' "$cmd" | grep -Eo 'git[[:space:]][^;&|]*push[^;&|]*' | tr ' ' '\037'); do
  seg=$(printf '%s' "$seg" | tr '\037' ' ')
  if printf '%s' "$seg" | grep -Eq '(^|[[:space:]])(-f|--force|--force-with-lease[^[:space:]]*|--force-if-includes|-d|--delete|--mirror|--prune)([[:space:]]|$)|[[:space:]]\+[A-Za-z0-9_./-]|[[:space:]]:[A-Za-z0-9_./-]'; then
    echo "ЗАБЛОКИРОВАНО: перезапись или удаление истории на GitHub. Обычная отправка (git push origin <ветка>) разрешена; перезаписать или удалить — только сам Роман, если это действительно нужно." >&2
    exit 2
  fi
done
# 4. HTTP-запросы, меняющие данные на живом сайте (читать сайт можно)
if printf '%s' "$cmd" | grep -Eq '(curl|wget)' && printf '%s' "$cmd" | grep -Eiq "$hosts"; then
  printf '%s' "$cmd" | grep -Eq '(^|[[:space:]])(-X|--request|-d|--data[a-z-]*|-F|--form[a-z-]*|-T|--upload-file|--post-data|--post-file)([[:space:]=]|$)' \
    && block "запрос, меняющий данные на сайте"
fi

exit 0
