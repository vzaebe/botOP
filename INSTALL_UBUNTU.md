# Запуск бота на Ubuntu без Docker

## Требования
- Ubuntu с доступом в интернет
- Python 3.10+ (`python3 --version`)
- Права на установку пакетов (`sudo`)

## Установка
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

## Развёртывание
```bash
mkdir -p ~/bot && cd ~/bot
# Скопируйте сюда исходники (scp/git/rsync)

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Конфигурация
```bash
cp env.example .env
nano .env   # укажите BOT_TOKEN, ADMIN_IDS, ADMIN_PASSWORD, PERSONAL_DATA_LINK
```
Обязательно ревокните старый токен и задайте новый пароль.

## Запуск (foreground)
```bash
source .venv/bin/activate
python -m bot.main
```
Проверьте в Telegram: /start.

## Автозапуск через systemd (опционально)
```bash
sudo tee /etc/systemd/system/telegram-bot.service >/dev/null <<'EOF'
[Unit]
Description=Telegram Event Bot
After=network.target

[Service]
WorkingDirectory=/home/USER/bot
ExecStart=/home/USER/bot/.venv/bin/python -m bot.main
EnvironmentFile=/home/USER/bot/.env
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable telegram-bot.service
sudo systemctl start telegram-bot.service
journalctl -u telegram-bot.service -f
```
Замените `/home/USER/bot` на ваш путь.

## Обновление
```bash
cd ~/bot
source .venv/bin/activate
git pull    # если проект из git
pip install -r requirements.txt
systemctl restart telegram-bot.service  # если используете systemd
```
