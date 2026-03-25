#!/bin/bash

# MedBot Production Deployment Script

set -e

echo "🚀 MedBot Production Deployment"
echo "================================"

# Check if .env.production exists
if [ ! -f .env.production ]; then
    echo "❌ Error: .env.production file not found"
    echo "   Please create it from .env.production.template:"
    echo "   cp .env.production.template .env.production"
    echo "   Then edit .env.production with your values"
    exit 1
fi

# Load environment variables
set -a
source .env.production
set +a

# Check required environment variables
REQUIRED_VARS=("SECRET_KEY" "POSTGRES_PASSWORD")
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: $var is not set in .env.production"
        exit 1
    fi
done

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p nginx/ssl logs faiss_index Data

# Generate self-signed SSL cert if not exists (for testing)
if [ ! -f nginx/ssl/cert.pem ]; then
    echo "🔐 Generating self-signed SSL certificate (replace with real cert in production)..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx/ssl/privkey.pem \
        -out nginx/ssl/fullchain.pem \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost" \
        2>/dev/null || echo "⚠️  OpenSSL not available, skipping SSL cert generation"
fi

# Build and start services
echo "🐳 Building Docker images..."
docker-compose -f docker-compose.production.yml build

echo "🚀 Starting services..."
docker-compose -f docker-compose.production.yml up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check health
echo "🏥 Checking service health..."
docker-compose -f docker-compose.production.yml ps

# Initialize database if needed
echo "📊 Initializing database..."
docker-compose -f docker-compose.production.yml exec -T medbot python -c "
from src.database_multitenant import init_multitenant_db
init_multitenant_db()
print('✅ Database initialized')
" || echo "ℹ️  Database already initialized"

# Show status
echo ""
echo "✅ MedBot is now running!"
echo ""
echo "📍 Services:"
echo "   - Application: http://localhost"
echo "   - Health check: http://localhost/health"
echo "   - Operator dashboard: http://localhost/operator"
echo ""
echo "📝 View logs:"
echo "   docker-compose -f docker-compose.production.yml logs -f medbot"
echo ""
echo "🛑 Stop services:"
echo "   docker-compose -f docker-compose.production.yml down"
echo ""
