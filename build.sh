#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "📦 Installing Python dependencies..."
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

echo "🎨 Collecting static files..."
python manage.py collectstatic --no-input

echo "🗄️ Running database migrations..."
python manage.py migrate

echo "🌱 Seeding initial hotel database..."
python seed_all_data.py || true

echo "✅ Render build completed successfully!"
