#!/usr/bin/env bash
#
# Usage:
#   sudo ./setup.sh <DOMAIN> <APP_PORT>
#
# Example:
#   sudo ./setup.sh flaskapp.problem.li 5000
#
# This script will:
#   1) Parse the subdomain to derive the app/user name (e.g. "flaskapp" from "flaskapp.problem.li")
#   2) Create a dedicated Linux user if it doesn't exist
#   3) Install required packages (python3-venv, certbot, nginx, etc.)
#   4) Create a Python virtual environment in /opt/<appname>
#   5) Install gunicorn in that venv
#   6) Create an NGINX config that proxies requests to gunicorn on <APP_PORT>
#   7) Obtain and configure an SSL certificate with certbot
#   8) Create and enable a systemd service to run your Flask app
#
# Make sure your Flask code is placed or cloned into /opt/<appname> after running this script.

set -e

DOMAIN="$1"
APP_PORT="$2"

# Validate input
if [[ -z "$DOMAIN" || -z "$APP_PORT" ]]; then
    echo "Usage: sudo $0 <DOMAIN> <APP_PORT>"
    exit 1
fi

# Extract the app/user name from the first subdomain (part before the first dot)
APP_NAME="$(echo "$DOMAIN" | cut -d '.' -f1)"
# We use the same name for the dedicated system user
APP_USER="$APP_NAME"

# We'll install everything under /opt/<appname>
INSTALL_DIR="/opt/$APP_NAME"

# Systemd service filename
SERVICE_NAME="${APP_NAME}.service"
# NGINX config filename
NGINX_CONF_NAME="${APP_NAME}.conf"
FLASK_APP_MODULE="${APP_NAME}:app"

echo "--------------------------------------------------------"
echo "Domain:       $DOMAIN"
echo "Subdomain:    $APP_NAME"
echo "App/User:     $APP_USER"
echo "Port:         $APP_PORT"
echo "Install Dir:  $INSTALL_DIR"
echo "Flask App:    $FLASK_APP_MODULE"
echo "--------------------------------------------------------"
echo "Ensure DNS is pointing to this server for $DOMAIN."
echo "Press ENTER to continue or CTRL+C to abort."
read

echo "1) Creating user '$APP_USER' if it does not exist..."
if ! id "$APP_USER" &>/dev/null; then
    adduser --system --no-create-home --group "$APP_USER"
fi

echo "2) Installing required packages..."
sudo apt-get update
sudo apt-get install -y certbot nginx
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

echo "3) Creating /opt/$APP_NAME and Python virtual environment..."
mkdir -p "$INSTALL_DIR"
if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
    uv venv "$INSTALL_DIR/.venv"
fi

echo "4) Activating venv and installing gunicorn..."
source "$INSTALL_DIR/.venv/bin/activate"
uv pip install -r requirements.txt
deactivate

echo "5) Writing NGINX config to /etc/nginx/sites-available/$NGINX_CONF_NAME..."
NGINX_CONFIG="/etc/nginx/sites-available/$NGINX_CONF_NAME"
sudo tee "$NGINX_CONFIG" <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    access_log /var/log/nginx/$APP_NAME-access.log;
    error_log /var/log/nginx/$APP_NAME-error.log;
}
EOF

echo "6) Enabling site and restarting nginx..."
sudo ln -sf "$NGINX_CONFIG" "/etc/nginx/sites-enabled/$NGINX_CONF_NAME"
sudo systemctl restart nginx

echo "7) Obtaining SSL certificate with certbot..."
# The --nginx plugin will modify the NGINX config for HTTPS automatically.
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" || {
    echo "Certbot failed. Check DNS and logs. Continuing..."
}

echo "8) Creating systemd service /etc/systemd/system/$SERVICE_NAME..."
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
sudo tee "$SERVICE_FILE" <<EOF
[Unit]
Description=Gunicorn instance to serve $APP_NAME Flask app
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/gunicorn -w 4 -b 127.0.0.1:$APP_PORT $FLASK_APP_MODULE
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo "9) Setting ownership of $INSTALL_DIR to $APP_USER:$APP_USER..."
sudo chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR"

echo "10) Enabling and starting $SERVICE_NAME..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME"

echo ""
echo "--------------------------------------------------------"
echo "Deployment complete!"
echo "Your Flask app should be reachable at: https://$DOMAIN/"
echo "Files are located in: $INSTALL_DIR"
echo "NGINX config:         $NGINX_CONFIG"
echo "systemd service:      $SERVICE_FILE"
echo "--------------------------------------------------------"
echo "Check your service logs with: journalctl -u $SERVICE_NAME -f"
echo "--------------------------------------------------------"
