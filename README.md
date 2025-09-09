# Lab Tutor - Neo4j Database Setup

## Quick Start

To start the Neo4j database:

```bash
docker-compose up -d neo4j
```

To start all services (when you add more):

```bash
docker-compose up -d
```

## Access Neo4j

- **Neo4j Browser**: http://localhost:7474
- **Bolt Connection**: bolt://localhost:7687
- **Credentials**: 
  - Username: `neo4j`
  - Password: `password123`

## Useful Commands

```bash
# Build and start services
docker-compose up -d --build

# View logs
docker-compose logs -f neo4j

# Stop services
docker-compose down

# Stop and remove volumes (WARNING: This will delete your data)
docker-compose down -v

# Access Neo4j shell
docker-compose exec neo4j cypher-shell -u neo4j -p password123
```

## Configuration

Environment variables can be modified in the `.env` file.

## Adding New Services

When adding new services, add them to the `docker-compose.yml` file and ensure they use the `lab_tutor_network` network to communicate with Neo4j.
