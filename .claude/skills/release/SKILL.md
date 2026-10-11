---
name: release
description: Подготовить выкладку kireevonline.ru — проверки, проверка обратимости миграций на копии базы сайта, сохранение версии в main на GitHub, одна команда для Романа простыми словами, проверка живого сайта после выкладки. Использовать, когда изменения готовы и Роман их одобрил («выкладываем», «давай на сайт»).
---

# Подготовка выкладки

Выкладывает **только Роман** своей командой. Claude готовит версию и проверяет сайт до и после.
Запуск `deploy/deploy.py`, `deploy/rollback.py`, `deploy/setup_readonly.py` и прямой ssh на сервер блокирует хук
`~/.claude/hooks/kireevonline-guard.sh` — не обходить. Ложное срабатывание (имя скрипта в тексте команды) —
переформулировать или править файл через Edit.

## 1. Свежий бэкап
`python3 deploy/backup.py` — база и новые фото с сайта на Mac (сервер только читается).

## 2. Проверки
1. `../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .`
2. `../.venv/bin/python manage.py test photos`
3. `../.venv/bin/python -m unittest discover -s deploy/tests -t .` — выкладка, откат, автовозврат на копии
   сервера и проверка блокировки (около 2 минут).
4. Скил `browser-check`: «Барабан», альбом, панель, шапка — компьютер и телефон.

## 3. Если меняется база (есть новые файлы в `photos/migrations/`)
Миграции только обратимые, иначе не сработает откат. Проверить на копии свежей базы сайта:
```bash
SIM=$(mktemp -d) && cp "$(ls -t ../backups/db/*_server.sqlite3 | head -1)" "$SIM/db.sqlite3"
export KO_SIM_DIR=$SIM PYTHONPATH=.claude/skills/release/scripts DJANGO_SETTINGS_MODULE=sim_settings
dump() { sqlite3 "$SIM/db.sqlite3" .dump | grep -v -e '^INSERT INTO auth_permission' -e '^INSERT INTO sqlite_sequence' | sort; }
dump > "$SIM/before.sql"
../.venv/bin/python manage.py migrate photos                    # вперёд
../.venv/bin/python manage.py migrate photos <шаг, что на сайте>  # назад
dump | diff - "$SIM/before.sql" && echo "откат вернул данные как были"
../.venv/bin/python manage.py migrate photos                    # и снова вперёд
```
Сравнение — по отсортированному дампу без служебных прав Django и счётчиков: после миграции Django сам
добавляет права для новых моделей и при откате их не удаляет, а пересобранные таблицы меняют порядок в файле.
Шаг, что на сайте, — `python3 deploy/status.py` (версия) и `git show <версия>:photos/migrations/`.

## 4. Версия на GitHub
Рабочая ветка → `main` без слияний поверх чужого: `git switch main && git merge --ff-only <ветка> && git push origin main`.
Хук `.githooks/pre-commit` сам прогонит стиль и тесты; на GitHub — `.github/workflows/tests.yml`.
Выкладывается ровно `origin/main`; выкладка сама ещё раз прогонит автотесты на этой версии.

## 5. Сообщение Роману
- Простыми словами, что изменится для посетителей и для него.
- **Отдельно предупредить**, если меняется структура базы (миграции) или библиотеки (`requirements.txt`).
- Команда — одним блоком `bash`:
  ```bash
  cd ~/"Claude Code/kireevonline/gallery" && python3 deploy/deploy.py
  ```
- Шаги буквально: «напиши `да` и нажми Enter»; с VPN проверка сайта может идти до 6 минут — это нормально.
- Если скрипт написал «Покажите это сообщение Claude» — разбирать по тексту, ничего не трогая на сервере.

## 6. После выкладки
- `python3 deploy/status.py` — на сервере новая версия, журнал выкладки «OK».
- Живой сайт как посетитель (только GET; версия — заголовок `X-Site-Version`): `/`, альбом, `/shuffle/`,
  `/about/`, `/robots.txt`, `/sitemap.xml`. Через VPN запросы иногда висят 16–40 с — повторять.
- Коротко отчитаться Роману; важные решения — в `docs/decisions.md`.
