# gunicorn.conf.py
import os

# Port to bind to
port = os.environ.get("PORT", "8080")
bind = f"0.0.0.0:{port}"

# Only use 1 worker process to avoid starting multiple Discord Bot threads
workers = 1

# Use threads for handling concurrent Flask requests
threads = 4

# Increase timeout to 120 seconds to prevent Gunicorn from killing the worker
# while the Discord bot is logging in and syncing slash commands
timeout = 120

# Keepalive connection timeout
keepalive = 5
