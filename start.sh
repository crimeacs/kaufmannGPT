#!/bin/bash

# AI Stand-up Comedy Agent - Quick Start Script

set -e

echo "🎭 AI Stand-up Comedy Agent - Starting..."
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed"
    echo "   Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: Docker Compose is not installed"
    echo "   Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Check for API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  Warning: OPENAI_API_KEY environment variable not set"
    echo ""
    echo "   Please set your API key:"
    echo "   export OPENAI_API_KEY='your-key-here'"
    echo ""
    echo "   Or create a .env file with:"
    echo "   OPENAI_API_KEY=your-key-here"
    echo ""
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Build and start services
echo "🔨 Building Docker images..."
docker-compose build

echo ""
echo "🚀 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 5

# Check health
AUDIENCE_HEALTH=$(curl -s http://localhost:8002/health 2>&1 || echo "failed")
JOKE_HEALTH=$(curl -s http://localhost:8003/health 2>&1 || echo "failed")

echo ""
echo "📊 Service Status:"
echo "─────────────────────────────────────"

if [[ $AUDIENCE_HEALTH == *"healthy"* ]]; then
    echo "✅ Audience Service: http://localhost:8002"
else
    echo "❌ Audience Service: Not responding"
fi

if [[ $JOKE_HEALTH == *"healthy"* ]]; then
    echo "✅ Joke Service: http://localhost:8003"
else
    echo "❌ Joke Service: Not responding"
fi

echo "✅ Frontend: http://localhost:3002"
echo ""
echo "─────────────────────────────────────"
echo ""
echo "🎉 All services started!"
echo ""
echo "📱 Open your browser:"
echo "   http://localhost:3002"
echo ""
echo "📋 View logs:"
echo "   docker-compose logs -f"
echo ""
echo "🛑 Stop services:"
echo "   docker-compose down"
echo ""
