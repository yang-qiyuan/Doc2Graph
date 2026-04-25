package config

import "os"

type Config struct {
	HTTPAddr string
	Neo4j    Neo4jConfig
}

type Neo4jConfig struct {
	URI      string
	Username string
	Password string
	Database string
}

func Load() Config {
	addr := os.Getenv("DOC2GRAPH_HTTP_ADDR")
	if addr == "" {
		addr = ":8080"
	}

	neo4jURI := os.Getenv("NEO4J_URI")
	if neo4jURI == "" {
		neo4jURI = "bolt://localhost:7687"
	}

	neo4jUser := os.Getenv("NEO4J_USER")
	if neo4jUser == "" {
		neo4jUser = os.Getenv("NEO4J_USERNAME") // fallback
		if neo4jUser == "" {
			neo4jUser = "neo4j"
		}
	}

	neo4jPassword := os.Getenv("NEO4J_PASSWORD")
	if neo4jPassword == "" {
		neo4jPassword = "password"
	}

	neo4jDatabase := os.Getenv("NEO4J_DATABASE")
	if neo4jDatabase == "" {
		neo4jDatabase = "neo4j"
	}

	return Config{
		HTTPAddr: addr,
		Neo4j: Neo4jConfig{
			URI:      neo4jURI,
			Username: neo4jUser,
			Password: neo4jPassword,
			Database: neo4jDatabase,
		},
	}
}
