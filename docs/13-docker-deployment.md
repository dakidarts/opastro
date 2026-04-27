# Docker Deployment

OpAstro ships a `Dockerfile` and `docker-compose.yml` for containerized deployment.

## Quick Start

```bash
docker compose up --build
```

Services:
- **API** on `http://localhost:8000` with hot reload enabled
- **Redis** on `localhost:6379` (optional; configure `REDIS_URL` to use)

## Dockerfile

The image is based on `python:3.12-slim` and includes:
- Cairo / Pango system libraries for SVG/PNG/PDF rendering
- Editable package install from source
- `PYTHONPATH=/app/src`
- Default SQLite cache at `/app/data/cache.sqlite`

## Configuration via Environment

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - OPASTRO_RATE_LIMIT_RPS=20
      - OPASTRO_RATE_LIMIT_BURST=40
      - OPASTRO_REQUIRE_API_KEY=0
      - PREGEN_TOKEN=${PREGEN_TOKEN}
    volumes:
      - ./data:/app/data
```

## Production Considerations

- **Disable reload**: Remove `--reload` from the API command.
- **Use Redis**: Set `REDIS_URL` for shared caching across replicas.
- **API keys**: Enable `OPASTRO_REQUIRE_API_KEY=1` and set `OPASTRO_API_KEYS`.
- **Rate limits**: Tune `OPASTRO_RATE_LIMIT_RPS` and `OPASTRO_RATE_LIMIT_BURST` based on load.
- **SSL/TLS**: Place behind a reverse proxy (nginx, Traefik, etc.) for TLS termination.

## Health Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

## Building for Distribution

```bash
docker build -t opastro:latest .
docker run -p 8000:8000 -e OPASTRO_RATE_LIMIT_RPS=50 opastro:latest
```
