.PHONY: up down test api shell clean

up:
docker compose up -d
@echo "Waiting for services to be healthy..."
@sleep 10
docker compose ps

down:
docker compose down -v

test:
docker compose run --rm test-runner

api:
@echo "API running at http://localhost:8000"
@echo "Dashboard at http://localhost:8000/"
@echo "Docs at http://localhost:8000/docs"
curl -s http://localhost:8000/stats | python3 -m json.tool

shell:
docker compose exec testenv bash

clean:
docker compose down -v
docker system prune -f

build-deb:
docker compose exec testenv dpkg-deb --build /workspace/debian-pkg /workspace/archive-files.deb
@echo "Debian package created: archive-files.deb"

install-deb: build-deb
docker compose exec testenv dpkg -i /workspace/archive-files.deb

run-dev:
docker compose exec testenv python3 archive_files.py --group developers

run-ops:
docker compose exec testenv python3 archive_files.py --group ops

all: up test
@echo "All tests passed!"
