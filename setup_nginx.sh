#!/bin/bash
# Скрипт для настройки nginx для Telegram бота
# Использование: sudo bash setup_nginx.sh

set -e  # Остановка при ошибке

echo "🚀 Настройка nginx для Telegram бота..."
echo ""

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Запустите скрипт с sudo: sudo bash setup_nginx.sh"
    exit 1
fi

# Создаем бэкап текущего конфига
echo "📦 Создание бэкапа текущего конфига..."
cp /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ Бэкап создан"
echo ""

# Записываем новый конфиг
echo "📝 Обновление конфигурации nginx..."
cat > /etc/nginx/sites-available/default << 'EOF'
##
# Nginx configuration for Telegram AI Image Bot
##

# Default server configuration (catch-all)
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    
    root /var/www/html;
    index index.html index.htm index.nginx-debian.html;
    server_name _;
    
    location / {
        try_files $uri $uri/ =404;
    }
}

# Telegram Bot - Proxy to Docker container
server {
    listen 443 ssl;
    listen [::]:443 ssl ipv6only=on;
    server_name nkonshin7.ru;

    # SSL certificates managed by Certbot
    ssl_certificate /etc/letsencrypt/live/nkonshin7.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nkonshin7.ru/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Proxy all requests to Telegram bot running on port 8000
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}

# HTTP to HTTPS redirect for nkonshin7.ru
server {
    listen 80;
    listen [::]:80;
    server_name nkonshin7.ru;
    
    # Redirect all HTTP traffic to HTTPS
    return 301 https://$host$request_uri;
}
EOF

echo "✅ Конфигурация обновлена"
echo ""

# Проверка конфигурации
echo "🔍 Проверка конфигурации nginx..."
if nginx -t; then
    echo "✅ Конфигурация валидна"
    echo ""
else
    echo "❌ Ошибка в конфигурации!"
    echo "Восстанавливаем бэкап..."
    cp /etc/nginx/sites-available/default.backup.* /etc/nginx/sites-available/default
    exit 1
fi

# Перезапуск nginx
echo "🔄 Перезапуск nginx..."
systemctl reload nginx
echo "✅ Nginx перезапущен"
echo ""

# Проверка статуса
echo "📊 Статус nginx:"
systemctl status nginx --no-pager | head -5
echo ""

# Финальные проверки
echo "🧪 Проверка работоспособности..."
echo ""

# Проверка что nginx слушает порты
echo "Порты nginx:"
ss -tlnp | grep nginx || echo "⚠️  Nginx не слушает порты"
echo ""

echo "✅ Настройка завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Запустите бота: cd /путь/к/проекту && docker-compose up -d"
echo "2. Проверьте локально: curl http://localhost:8000/health"
echo "3. Проверьте через домен: curl https://nkonshin7.ru/health"
echo ""
echo "💡 Бэкап старого конфига сохранен в /etc/nginx/sites-available/"
