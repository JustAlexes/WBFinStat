# FinStat

Первый шаблон веб-приложения для финансовых отчётов Wildberries. Сервер написан на Django 5.2, локальные данные хранятся в SQLite.

## Первый запуск

Нужен Python 3.10 или новее. Откройте терминал в папке репозитория.

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Откройте http://127.0.0.1:8000/ в браузере. Для остановки сервера нажмите `Ctrl+C`.

Команда `migrate` создаёт локальную базу `db.sqlite3`. Файл базы и виртуальное окружение `.venv` не отправляются в GitHub.

В интерфейсе есть главная страница, сворачиваемое боковое меню и демонстрационный профиль. В меню пользователя находятся ссылки на профиль и настройки. В настройках можно выбрать светлую или тёмную тему; выбор сохраняется в браузере.

Для разработки приложение запускается с `DEBUG=True`; перед размещением в интернете потребуется отдельная настройка безопасности, включая `DJANGO_SECRET_KEY`.
