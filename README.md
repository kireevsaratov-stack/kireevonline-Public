# kireevonline.ru — фотогалерея на Django

Публичная копия кода личной фотогалереи [kireevonline.ru](https://kireevonline.ru): разделы, альбомы с записками,
полноэкранный просмотр, «Барабан» со случайными кадрами и собственная панель управления.

Проект сделан в режиме «ни строчки кода»: весь код написан с помощью Claude Code (AI-инструмент для разработки),
вручную код не писался и не читался. Цель — проверить, можно ли довести продукт до продакшена, опираясь
только на требования, автотесты и проверку результата. Продуктовые решения, тексты, приёмка и правила работы
с AI — мои.

**Сайт:** [kireevonline.ru](https://kireevonline.ru) · **Обзор проекта:** [kireevsaratov-stack.github.io/kireevonline-Public/overview.html](https://kireevsaratov-stack.github.io/kireevonline-Public/overview.html)

## Технологии

- **Backend:** Python 3.13, Django 5.2 (ORM, миграции, шаблоны, middleware, management commands), SQLite
- **Обработка изображений:** Pillow — проверка формата (JPEG/PNG/WebP), поворот по EXIF, удаление метаданных,
  сжатие, превью
- **Frontend:** HTML-шаблоны Django, CSS (адаптивная вёрстка, mobile-first), vanilla JavaScript (без фреймворков):
  justified-сетка, lightbox, свайпы, управление с клавиатуры, drag-and-drop, chunked upload
- **Загрузка файлов:** по частям (chunked upload) с повтором, идемпотентной сборкой и защитой от дублей
- **Безопасность:** Content Security Policy с nonce, HSTS, Permissions-Policy, rate limiting входа,
  журнал действий, security.txt, безопасные настройки по умолчанию
- **SEO:** sitemap.xml, robots.txt, Open Graph, Schema.org, canonical, meta description
- **Хостинг:** shared hosting, Apache + mod_wsgi, HTTPS
- **CI/CD:** GitHub Actions, git pre-commit hook, деплой одной командой с healthcheck и автоматическим откатом
  (rollback), снимки базы перед выкладкой, обратимые миграции
- **Тестирование:** Django TestCase / TransactionTestCase, unittest, mock, тесты деплоя на поддельном сервере,
  E2E-сценарии в headless Chrome через Chrome DevTools Protocol (Node.js)
- **Качество кода:** ruff (линтер и форматтер), закреплённые версии зависимостей, проверка сборок под сервер
- **Бэкапы:** снимки базы, архив для облака с контрольными суммами и проверенным восстановлением
- **Работа с AI:** Claude Code — инструкции проекта (`CLAUDE.md`), сценарии работы (`.claude/skills/`),
  доступ к серверу только для чтения, блокировка команд выкладки

## Что где лежит

| Папка | Что внутри |
|---|---|
| `config/` | настройки Django, адреса, защита (`security.py`), номер версии |
| `photos/` | приложение галереи: модели `Section`, `Album`, `Photo`; подготовка фото (`media.py`); страницы (`views/`); шаблоны; миграции; тесты |
| `static/` | стили, скрипты, шрифт Oswald |
| `deploy/` | выкладка, откат, бэкап, архив и их тесты |
| `browser_checks/` | сценарии в настоящем браузере (Chrome без окна) |
| `docs/` | устройство, решения с причинами, бэклог, отчёты перекрёстных проверок кода, разбор проекта |
| `CLAUDE.md`, `.claude/` | инструкции и сценарии (скилы) для Claude Code |
| `docs/ai-guard/` | копия блокировки команд для Claude Code (рабочая лежит вне проекта, чтобы её нельзя было ослабить правкой кода) |
| `.githooks/`, `.github/` | проверки перед сохранением версии и на GitHub |

С чего начать: [docs/architecture.md](docs/architecture.md) — как устроено,
[docs/decisions.md](docs/decisions.md) — почему так, [docs/reviews/](docs/reviews/) — перекрёстные проверки кода моделями GPT и Claude.

## Запуск локально

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python manage.py migrate
DJANGO_DEBUG=True python manage.py demo_data   # демо-разделы и картинки-заглушки для пустой базы
DJANGO_DEBUG=True python manage.py runserver
```

Тесты: `python manage.py test photos` и `python -m unittest discover -s deploy/tests -t .`.

## Чем эта копия отличается от рабочей

Это снимок кода без истории версий. Фото, база и тексты альбомов в репозиторий не входят; имя пользователя
и адрес сервера заменены заглушками. Рабочий репозиторий — приватный; эта копия обновляется из него.

Фотографии на сайте © Роман Киреев. Шрифт Oswald — SIL Open Font License (`static/fonts/OFL.txt`).
