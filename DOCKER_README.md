# AI Stand-up Comedy Agent - Docker Deployment Guide

Complete guide for running the AI Stand-up Comedy Agent using Docker containers.

## Architecture

```
┌─────────────────────────────────────────┐
│  Frontend (Port 3000)                   │
│  Nginx + Vite-built static files        │
│  - Debug console                        │
│  - Real-time logs                       │
└──────────┬──────────────────────────────┘
           │
     ┌─────┴──────┐
     │            │
     ▼            ▼
┌──────────┐  ┌──────────┐
│ Audience │  │   Joke   │
│ Service  │◄─┤  Service │
│ (8000)   │  │  (8001)  │
└──────────┘  └──────────┘
```

## Services

### 1. Audience Service (Port 8000)
- Analyzes audience reactions
- Stores reaction history
- Provides `/latest` endpoint for joke service
- Streams real-time logs via SSE

### 2. Joke Service (Port 8001)
- Generates jokes based on audience reactions
- Can auto-fetch reactions from audience service
- Provides performance statistics
- Streams real-time logs via SSE

### 3. Frontend (Port 3000)
- Debug console web interface
- Real-time log viewer
- API testing interface
- Auto-performance mode

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- OpenAI API key

## Quick Start

### 1. Set Your API Key

```bash
export OPENAI_API_KEY="your-openai-api-key-here"
```

Or create a `.env` file:
```bash
echo "OPENAI_API_KEY=your-key-here" > .env
```

### 2. Build and Start Services

```bash
docker-compose up --build
```

This will:
- Build all three containers
- Start services in order (audience → joke → frontend)
- Run health checks
- Expose ports 8000, 8001, and 3000

### 3. Access the Application

- **Frontend**: http://localhost:3000
- **Audience Service**: http://localhost:8000
- **Joke Service**: http://localhost:8001

## Docker Commands

### Start Services (Detached)
```bash
docker-compose up -d
```

### Stop Services
```bash
docker-compose down
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f audience-service
docker-compose logs -f joke-service
docker-compose logs -f frontend
```

### Restart a Service
```bash
docker-compose restart audience-service
docker-compose restart joke-service
```

### Rebuild After Code Changes
```bash
docker-compose up --build -d
```

### Check Service Status
```bash
docker-compose ps
```

### Access Service Shell
```bash
docker exec -it standup-audience-service /bin/sh
docker exec -it standup-joke-service /bin/sh
```

## Environment Variables

### Required
- `OPENAI_API_KEY` - Your OpenAI API key

### Optional
- `AUDIENCE_SERVICE_URL` - URL of audience service (default: `http://audience-service:8000`)

## Networking

All services are on the `standup-network` bridge network:
- Services can communicate using container names
- Example: Joke service reaches audience service at `http://audience-service:8000`

## Volumes

### Mounted Volumes
- `./logs` → `/app/logs` - Service logs
- `./audio_samples` → `/app/audio_samples` - Generated audio files

These directories persist between container restarts.

## Health Checks

Each service has health checks configured:
- Runs every 30 seconds
- 3 retries before marking unhealthy
- 10-second start period

Check health status:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

## API Endpoints

### Audience Service (Port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/latest` | Get latest reaction |
| GET | `/history` | Get reaction history |
| GET | `/stream/logs` | SSE log stream |
| POST | `/analyze` | Analyze audio |
| POST | `/analyze-file` | Analyze audio file |
| WS | `/ws/analyze` | WebSocket analysis |

### Joke Service (Port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/generate` | Generate joke (manual reaction) |
| POST | `/generate/auto` | Auto-generate (fetch reaction) |
| POST | `/generate/audio` | Generate with audio file |
| GET | `/stream/logs` | SSE log stream |
| GET | `/stats` | Performance statistics |
| POST | `/reset` | Reset generator |
| WS | `/ws/perform` | WebSocket performance |

## Testing the Setup

### 1. Check Services are Running
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

### 2. Test Audience Service
```bash
curl http://localhost:8000/latest
```

### 3. Test Joke Generation
```bash
curl -X POST http://localhost:8001/generate/auto
```

### 4. Open Frontend
```
http://localhost:3000
```

## Development Mode

For local development without Docker:

### 1. Start Backend Services
```bash
# Terminal 1 - Audience Service
cd src/api
python -m uvicorn audience_service:app --reload --port 8000

# Terminal 2 - Joke Service
cd src/api
python -m uvicorn joke_service:app --reload --port 8001
```

### 2. Start Frontend
```bash
cd frontend
npm install
npm run dev
```

## Troubleshooting

### Services Not Starting
```bash
# Check logs
docker-compose logs

# Check health
docker ps

# Restart services
docker-compose restart
```

### Port Already in Use
```bash
# Find process using port
lsof -i :8000
lsof -i :8001
lsof -i :3000

# Kill process or change port in docker-compose.yml
```

### API Key Not Working
```bash
# Verify environment variable
docker-compose config

# Check if key is set in container
docker exec standup-joke-service printenv OPENAI_API_KEY
```

### Frontend Can't Connect to Backend
- Check that backend services are running
- Verify ports are correctly exposed
- Check browser console for CORS errors

### Services Can't Communicate
```bash
# Check network
docker network ls
docker network inspect standup-network

# Verify service names resolve
docker exec standup-joke-service ping audience-service
```

## Production Deployment

### Using Docker Compose

1. Set production environment variables
2. Use production-ready configuration
3. Enable HTTPS with reverse proxy
4. Set up monitoring and logging

### Example with Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
    }

    location /api/audience {
        proxy_pass http://localhost:8000;
    }

    location /api/joke {
        proxy_pass http://localhost:8001;
    }
}
```

## Monitoring

### View Resource Usage
```bash
docker stats
```

### View Container Logs
```bash
# Tail logs
docker-compose logs -f --tail=100

# Export logs
docker-compose logs > system.log
```

### Health Monitoring
All services expose `/health` endpoints for monitoring systems.

## Cleanup

### Remove Containers
```bash
docker-compose down
```

### Remove Containers and Volumes
```bash
docker-compose down -v
```

### Remove Images
```bash
docker-compose down --rmi all
```

### Complete Cleanup
```bash
docker-compose down -v --rmi all
docker system prune -a
```

## Performance Tips

1. **Use BuildKit**: `DOCKER_BUILDKIT=1 docker-compose build`
2. **Multi-stage builds**: Already configured in Dockerfiles
3. **Layer caching**: Dependencies installed before code copy
4. **Resource limits**: Add to docker-compose.yml if needed

```yaml
services:
  joke-service:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

## Security Considerations

1. **Never commit `.env` file** with real API keys
2. **Use Docker secrets** for production
3. **Run containers as non-root** (future enhancement)
4. **Keep images updated**: `docker-compose pull && docker-compose up -d`

## Support

For issues:
1. Check logs: `docker-compose logs`
2. Verify health: `docker ps`
3. Test APIs directly with curl
4. Check GitHub issues

## License

MIT License
