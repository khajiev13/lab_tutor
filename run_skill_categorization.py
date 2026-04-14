"""
Main script to fetch concepts, categorize them into skills, and store in Neo4j.
This script should be run to execute the full categorization workflow.
"""

import json
import sys
import os
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from categorize_concepts_to_skills import (
    categorize_concepts_to_skills,
    save_categorization_to_file,
    create_skills_in_neo4j,
)

# Concepts fetched via MCP (from the conversation)
CONCEPTS = [
    "5vs", "acid properties", "active node/vertex", "aggregation", "aggregation table elimination",
    "aggregator", "ai era", "alternating least squares (als)", "anti-crawler protection", 
    "apache drill project", "apache spark", "apache spark mllib", "apriori algorithm",
    "asynchronous replication", "attribute construction", "availability (a in cap)", "base",
    "basically available", "batch processing", "biased random walk", "big data",
    "big data analysis tools", "big data computing system", "big data scale", "big data schema approach",
    "binning", "binning algorithm", "blob", "bolt", "breadth first",
    "bulk synchronous parallel (bsp) model", "business intelligence (bi) report", "cap theorem",
    "cc attack protection", "clustering algorithm", "collaborative filtering", "column storage structure",
    "column-based store", "combiner (combine() function)", "compression in hana",
    "computational simulation (third paradigm)", "computing engine", "computing platform and engine",
    "conceptual model", "consistency (c in cap)", "content based algorithm", "content-based filtering",
    "content-based filtering steps", "convolutional neural network,cnn", "correlation over causality",
    "cost function", "crossvalidator", "crud", "customized big data application",
    "data access layer (dal)", "data access object (dao)", "data blocks", "data cleaning",
    "data cleaning basis", "data collection", "data collection and modeling", "data discretization technology",
    "data distribution", "data flow graph model", "data generalization", "data integration",
    "data is like crude oil", "data loading methods", "data masking", "data mining algorithms",
    "data modeling", "data normalization", "data partition", "data preprocessing",
    "data processing platform", "data processing system", "data reduction",
    "data reduction (subtraction) technology", "data redundancy", "data specification",
    "data storage", "data storage architecture", "data storing system", "data transformation",
    "data transformation components", "data value conflict", "data-intensive computing challenges",
    "data-intensive paradigm (fourth paradigm)", "database schema approach", "deep learning",
    "deep neural network layers", "deep web", "delete completely duplicate records", "delta store",
    "depth first", "dikw pyramid", "dimensionality reduction", "directed acyclic graph (dag)",
    "disk-centric computing limitation", "distributed architecture model", "distributed by clause",
    "distributed computing", "distributed data storage", "distributed database/datawarehouse",
    "distributed file system", "distributed graph computing", "distribution strategy api",
    "document type usage", "document-oriented", "document-oriented nosql db", "domain knowledge approach",
    "domain-independent detection", "eager execution", "edge", "empirical science",
    "enterprise data warehouse", "equal depth binning", "equal-width binning", "era of big data",
    "estimator", "etl (extract, transform, load)", "evaluator", "eventual consistency",
    "external data", "feature engineering", "force-directed graph drawing", "four major technologies",
    "fourth paradigm of scientific research", "fruchterman-reingold algorithm", "full extraction",
    "full table comparison (md5)", "general deep web crawler", "gephi",
    "google's interactive computing engine", "government data", "gradient descent", "graph database",
    "graph database advantages and usage", "graph parallel computing engine", "graph partition",
    "graph-based", "hadoop", "hadoop scheduler", "hash table", "hdfs",
    "hdfs and mapreduce cluster", "human brain vs. computer role", "in-memory computing",
    "in-memory computing model", "incremental extraction", "insert-only approach (column store)",
    "internal data", "internet data", "iot data", "item-based collaborative filtering",
    "jobtracker", "json", "keras", "key value pair based", "key-value database",
    "key-value pair storage", "k-means clustering", "k-nearest neighbor",
    "large-scale concurrent processing (mpp) model", "latent factor", "lazy evolution (lazy evaluation)",
    "linear regression (simple regression)", "log comparison (cdc)", "logical model", "low value density",
    "machine learning algorithm", "mapreduce", "mapreduce batch processing model",
    "mapreduce calculation model", "mapreduce computing engine", "massively parallel processing (mpp)",
    "massively parallel processing in hana", "master node", "master-slave (master/slave) architecture",
    "materialized aggregations", "matrix factorization", "micro-batch stream processing system",
    "mirror scheme", "missing data processing", "mixed structure", "ml persistence",
    "multiple data sources - instance level problems", "multiple data sources - model level problems",
    "n(i)", "n(u)", "naive bayes algorithm", "naming conflict", "network big data", "networkx",
    "new model of generating/consuming data", "nimbus", "node", "nosql database",
    "odbc (open database connectivity)", "olap", "old model of generating/consuming data", "oltp",
    "opic (online page importance computation)", "orm (object/relation mapping)", "outliers (isolated points)",
    "pagerank", "paradigm", "parallel execution", "paramgridbuilder", "parammap",
    "partition tolerance (p in cap)", "partitioning", "pattern matching", "peer to peer",
    "perception stage", "physical model", "pipeline", "pregel", "principal component analysis pca",
    "pyspark", "quasi-structured data", "rdd action", "rdd transformation", "real-time analytics",
    "real-time analytics processing (rtap)", "recommendation system", "regression algorithm",
    "reinforcement learning (rl)", "relational database (rdbms)", "relay nodes",
    "repeat record cleaning", "resilient distributed dataset (rdd)", "robot detection",
    "row-based store", "s4 (simple, scalable streaming system)", "sap hana", "savedmodel",
    "seed url", "segments", "semi-structured data", "semi-supervised learning",
    "service data object (service data object) service middleware", "shared-nothing architecture (sn)",
    "shuffle phase", "similarity calculation methods", "single data source - instance level problems",
    "single data source - model level problems", "single data source error categories",
    "singular value decomposition (svd)", "six degrees of separation", "slave nodes", "slot",
    "smoothing", "social network", "social network analysis (sna)", "soft-state",
    "spark ecosystem components", "spark master-slave architecture", "spout", "star-schema",
    "state passing model", "storm", "stream computing model", "stream processing",
    "strong consistency", "structural conflict", "structured data", "superstep",
    "supervised learning", "supervisor", "support vector machine", "tasktracker",
    "tensor", "tensorflow", "tensorflow hub", "tensorflow lite", "tensorflow serving",
    "tensorflow.js", "tf.data", "tf.feature_column", "tf.function",
    "theoretical science (second paradigm)", "timestamp method", "topology", "tor",
    "tpu (tensor processing unit)", "transaction systems stage", "transfer learning",
    "transformer", "trigger method", "unified data access interface (udai)", "unstructured data",
    "unsupervised learning", "user-based collaborative filtering", "user-item rating matrix (r)",
    "user-generated content stage", "value", "variety", "velocity", "veracity", "volume",
    "weak consistency", "web crawler", "web crawler crawling strategy", "xml"
]


def main():
    """Main execution function."""
    print(f"Starting skill categorization for {len(CONCEPTS)} concepts...")
    
    # Categorize concepts
    result = categorize_concepts_to_skills(CONCEPTS)
    
    # Save to file
    save_categorization_to_file(result, "skill_categorization.json")
    
    # Generate queries (will be executed via MCP)
    queries = create_skills_in_neo4j(result)
    
    # Save queries to file for MCP execution
    query_data = {
        "skills": [
            {
                "skill_id": idx + 1,
                "skill_name": skill.skill_name,
                "concept_names": skill.concept_names,
                "concept_count": len(skill.concept_names)
            }
            for idx, skill in enumerate(result.skills)
        ],
        "total_skills": len(result.skills),
        "total_concepts": sum(len(skill.concept_names) for skill in result.skills)
    }
    
    with open("skill_categorization_queries.json", "w", encoding="utf-8") as f:
        json.dump(query_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Categorization complete!")
    print(f"   - Generated {len(result.skills)} skills")
    print(f"   - Categorized {sum(len(skill.concept_names) for skill in result.skills)} concepts")
    print(f"   - Results saved to skill_categorization.json")
    print(f"   - Query data saved to skill_categorization_queries.json")
    print(f"\nNext step: Execute the Cypher queries via MCP to store skills in Neo4j")


if __name__ == "__main__":
    main()
