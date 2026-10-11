---
name: backup
description: Полный бэкап kireevonline.ru для облака — база и все фото с сайта на Mac, архив «под ключ» с инструкцией по восстановлению, проверка распаковкой, отдельный архив заметок. Использовать по просьбе Романа («сделай бэкап»), раз в месяц и после больших загрузок фото.
---

# Бэкап для облака

Сервер только читается (шлюз чтения). Паролей и учётных записей в архиве нет.

## 1. Скачать и собрать
```bash
python3 deploy/backup.py && python3 deploy/archive.py
```
`backup.py` докачивает только новое: база → `../backups/db/`, фото → `../backups/media/`.
`archive.py` кладёт архив в `../backups/archives/kireevonline-backup-<дата>.zip` (~1,5 ГБ).

## 2. Проверить распаковкой — не пропускать
```bash
S=$(mktemp -d) && cd "$S" && unzip -q "<путь к архиву>" && cd kireevonline-backup-*
shasum -a 256 -c SHA256SUMS.txt | awk '{print $NF}' | sort | uniq -c     # все строки — OK
git clone -q code/gallery.bundle "$S/g" && git -C "$S/g" branch -a       # код со всеми ветками
cd "<gallery>" && python3 deploy/verify_backup.py "$S/kireevonline-backup-<дата>"   # у каждого фото есть файл
rm -rf "$S"
```
Файл контрольных сумм называется `SHA256SUMS.txt` — проверять именно его (без файла `shasum` молча ничего не делает).

## 3. Заметки — отдельно
В архив сайта не входят: `notes/albums/` (ответы Романа к альбомам — личное) и прочие заметки.
```bash
cd ~/"Claude Code/kireevonline" && zip -qr backups/archives/kireevonline-notes-<дата>.zip notes -x "*.DS_Store"
```

## 4. Сказать Роману
Где лежат оба файла, размер, что проверено; что в архиве заметок личное. Загружает в облако Роман сам.
Если всё потеряно: архив из облака + «вот архив бэкапа сайта, восстанови его» → `ВОССТАНОВЛЕНИЕ.md` внутри архива.
