#!/bin/bash

# Production Deployment Script for KODI3
echo "🚀 Starting KODI3 Production Deployment..."

# Create necessary directories
mkdir -p logs
mkdir -p nginx/ssl

# Set permissions
chmod +x manage.py
chmod 755 logs

# Collect static files
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput --settings=kodi_core.production_settings

# Apply database migrations
echo "🗄️ Applying database migrations..."
python manage.py migrate --settings=kodi_core.production_settings

# Create superuser if needed
echo "👤 Creating superuser..."
python manage.py shell --settings=kodi_core.production_settings << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('admin', 'admin@kodi-phase2.onrender.com', 'admin123')
    print("Superuser created")
else:
    print("Superuser already exists")
EOF

# Build and start Docker containers
echo "🐳 Starting Docker containers..."
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

# Wait for database to be ready
echo "⏳ Waiting for database..."
sleep 30

# Check health
echo "🏥 Checking application health..."
sleep 10
curl -f http://localhost/health/ || exit 1

echo "✅ Deployment completed successfully!"
echo "🌐 Application is running at: https://kodi-phase2.onrender.com"
echo "📊 Monitor logs with: docker-compose -f docker-compose.prod.yml logs -f"
echo "🔧 Manage with: docker-compose -f docker-compose.prod.yml exec web python manage.py"

# Show running containers
echo "📋 Running containers:"
docker-compose -f docker-compose.prod.yml ps
