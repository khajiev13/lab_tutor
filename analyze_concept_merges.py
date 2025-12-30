#!/usr/bin/env python3
"""
Analyze concept merges by comparing before/after lists.
"""

before = [
    "5vs", "acid", "aggregate value", "aggregation", "aggregation tables", "ai era", 
    "alternating least square (als)", "anomaly detection", "apache drill", "apache giraph", 
    "apache graphlab", "apache spark core", "apriori algorithm", "asynchronous replication", 
    "attribute construction", "availability (a)", "base", "basically available", "batch processing", 
    "big data", "big data computing system", "big data era change", "binning algorithm", 
    "blob (binary large objects)", "bolt", "breadth first", "bulk synchronous parallel (bsp) model", 
    "business intelligence report", "cap theorem", "cc attack (challenge collapsar attack)", 
    "checkpoint mechanism", "cleaning of missing data", "clustering algorithm", 
    "collaborative filtering", "column-based", "column-oriented database", "columnar storage", 
    "combine function", "compression", "computer correlation analysis", "computing engine", 
    "computing platform and engine", "concept hierarchy", "conceptual data model", "consistency (c)", 
    "content-based filtering", "convolutional neural network (cnn)", "cosine similarity", 
    "cost function", "crossvalidator", "dark web", "data access layer (dal)", 
    "data access object (dao)", "data analysis tools", "data block", "data cleaning", 
    "data collection", "data cube", "data cube aggregation", "data discretization", 
    "data distribution", "data exhaust", "data generalization", "data governance", 
    "data integration", "data masking", "data mining algorithms", "data modeling", 
    "data node", "data normalization", "data partition", "data processing platform", 
    "data reduction", "data redundancy", "data scale", "data specification", 
    "data storage systems", "data transformation", "data transformation components", 
    "data value conflict", "data visualization tools", "data-intensive scientific discovery", 
    "dataflow graph", "datastreamer", "decision tree (decision tree) induction", 
    "deduplication", "deep learning", "deep web", "depth first", "dfsinputstream", 
    "dikw pyramid", "dimension reduction", "dimensionality reduction", 
    "directed acyclic graph (dag)", "discretization", "distributed architecture model", 
    "distributed computing", "distributed file system (dfs)", "distribution strategy api", 
    "document-oriented", "document-oriented database", "domain-independent detection", 
    "dsm (decomposition storage model)", "eager execution", "earth scope", 
    "eliminating noise data", "enterprise data warehouse", "equal depth binning", 
    "equal-width binning", "estimator", "etl (extract, transform, load)", "evaluator", 
    "eventual consistency", "external data", "fan-out urls", "feature engineering", 
    "first data then try to find the suitable schema", "first paradigm of scientific research", 
    "first schema, then data", "force-directed graph drawing", "form classifier", 
    "four major technologies", "fourth paradigm human-computer role", 
    "fourth paradigm of scientific research", "fruchterman-reingold algorithm", 
    "full extraction", "full table comparison (md5 check code)", "general deep web crawler", 
    "gephi", "google pregel", "google's interactive computing engine", "government data", 
    "gradient descent", "graph database", "graph parallel computing engine", "graph-based", 
    "graphx", "greenplum", "grid search", "hadoop", "hana", "hdfs", "hql", 
    "iceberg metaphor", "immutable data (in hdfs)", "in-memory computing", 
    "in-memory computing model", "in-memory database", "incorporate iot data collection", 
    "incremental extraction", "insert only approach", "instance-level data quality problems", 
    "integrity constraints", "internal data resources", "internet data authenticity and quality", 
    "intra-query fault tolerance", "iot data", "iot data collection", "it progress", 
    "item-based filtering", "item-item matrix", "k-means clustering", "k-nearest neighbor", 
    "keras api", "kettle", "key value pair based", "key-value database", 
    "large-scale concurrent processing (mpp-massively parallel processing) model", 
    "latent factors", "linear regression", "linear regression (simple regression)", 
    "log comparison (cdc)", "logical data model", "lossless compression", "lossy compression", 
    "low value density", "machine learning", "machine learning algorithms", "mapreduce", 
    "mapreduce batch processing model", "mapreduce calculation model", "mapreduce computing engine", 
    "massively parallel graph computation", "massively parallel processing (mpp)", "master node", 
    "master-slave", "materialized aggregations", "matrix factorization", 
    "micro-batch stream processing system", "min-max normalization", "mirror scheme", 
    "missing data processing", "missing value cleaning", "mixed structure", "ml persistence", 
    "ml pipelines", "mllib (machine learning library)", "model-level data quality problems", 
    "multiple data sources", "naive bayes algorithm", "name node", "naming conflict", 
    "network big data", "networkx", "new model of generating/consuming data", "nimbus", 
    "nodes and edges", "noisy data processing", "nosql database", 
    "odbc (open database connectivity)", "olap", "old model of generating/consuming data", 
    "oltp", "opic", "orm (object/relation mapping)", "pagerank", "paradigm", 
    "parameter tuning", "paramgridbuilder", "partition", "partition tolerance (p)", 
    "partitioning", "pattern matching", "peer to peer", "perception stage", "persistence", 
    "physical data model", "pipeline", "principal component analysis (pca)", "projection", 
    "quasi-structured data", "query interface recognition", "rdd (resilient distributed dataset)", 
    "rdd action", "rdd transformation", "real-time analytics", "recommendation system", 
    "reduce the amount of data", "regression algorithm", "reinforcement learning", 
    "relational database (rdbms)", "remove gradually backward attributes subset selection", 
    "repeat record cleaning", "row-based store", "rtap", 
    "s4 (simple, scalable streaming system)", "savedmodel", "second paradigm of scientific research", 
    "secondary name node", "seed url", "segment/slave node", "self-operated data", 
    "semi-structured data", "semi-supervised learning", "shared-nothing architecture", 
    "single data source", "singular value decomposition (svd)", "six degrees of separation", 
    "slot", "smoothing methods (binning, clustering, regression)", "social network", 
    "social network analysis (sna)", "soft-state", "spark", "spark architecture", 
    "spark mllib", "spark sql", "spark streaming", "spout", "standardization of decimal calibration", 
    "star-schema", "state passing model", "step forward attributes subset selection", "storm", 
    "stream computing model", "stream processing", "strong consistency", "structural conflict", 
    "structured data", "superstep", "supervised learning", "supervisor", 
    "support vector machine", "surface web", "tensor", "tensorflow", 
    "tensorflow processing unit (tpu)", "tf.function", "third paradigm human-computer role", 
    "third paradigm of scientific research", "timestamp method", "topology", 
    "tor (the onion router)", "transaction systems stage", "transformer", "triggers method", 
    "udal (unified data access layer)", "unified data access interface (udai)", 
    "unstructured data", "unsupervised learning", "user profile", "user-based filtering", 
    "user-generated content stage", "user-user similarity matrix", "value", 
    "variational autoencoder", "variety", "velocity", "veracity", "virtualization technology", 
    "volume", "waf (web application firewall)", "weak consistency", "web crawler", 
    "web crawler crawling process", "write pipeline (hdfs)", 
    "zero-mean normalization (z-score normalization)"
]

after = [
    "5vs", "acid", "aggregate value", "aggregation", "aggregation tables", "ai era", 
    "alternating least squares (als)", "anomaly detection", "apache drill", "apache giraph", 
    "apache graphlab", "apache spark core", "apriori algorithm", "asynchronous replication", 
    "attribute construction", "availability (a)", "base", "basically available", "batch processing", 
    "big data", "big data computing system", "big data era change", "binning algorithm", 
    "blob (binary large objects)", "bolt", "breadth first", "bulk synchronous parallel (bsp) model", 
    "business intelligence report", "cap theorem", "cc attack (challenge collapsar attack)", 
    "checkpoint mechanism", "clustering algorithm", "collaborative filtering", 
    "column-oriented database", "combine function", "compression", "computer correlation analysis", 
    "computing engine", "computing platform and engine", "concept hierarchy", "conceptual data model", 
    "consistency (c)", "content-based filtering", "convolutional neural network (cnn)", 
    "cosine similarity", "cost function", "crossvalidator", "dark web", "data access layer (dal)", 
    "data access object (dao)", "data analysis tools", "data block", "data cleaning", 
    "data collection", "data cube", "data cube aggregation", "data discretization", 
    "data distribution", "data exhaust", "data generalization", "data governance", 
    "data integration", "data masking", "data mining algorithms", "data modeling", 
    "data node", "data normalization", "data partition", "data processing platform", 
    "data reduction", "data redundancy", "data scale", "data specification", 
    "data storage systems", "data transformation", "data transformation components", 
    "data value conflict", "data visualization tools", "data-intensive scientific discovery", 
    "dataflow graph", "datastreamer", "decision tree (decision tree) induction", 
    "deduplication", "deep learning", "deep web", "depth first", "dfsinputstream", 
    "dikw pyramid", "dimension reduction", "directed acyclic graph (dag)", 
    "distributed architecture model", "distributed computing", "distributed file system (dfs)", 
    "distribution strategy api", "document-oriented database", "domain-independent detection", 
    "dsm (decomposition storage model)", "eager execution", "earth scope", 
    "enterprise data warehouse", "equal depth binning", "equal-width binning", "estimator", 
    "etl (extract, transform, load)", "evaluator", "eventual consistency", "external data", 
    "fan-out urls", "feature engineering", "first data then try to find the suitable schema", 
    "first paradigm of scientific research", "first schema, then data", 
    "force-directed graph drawing", "form classifier", "four major technologies", 
    "fourth paradigm human-computer role", "fourth paradigm of scientific research", 
    "fruchterman-reingold algorithm", "full extraction", "full table comparison (md5 check code)", 
    "general deep web crawler", "gephi", "google pregel", "google's interactive computing engine", 
    "government data", "gradient descent", "graph database", "graph parallel computing engine", 
    "graph-based", "graphx", "greenplum", "grid search", "hadoop", "hana", "hdfs", "hql", 
    "iceberg metaphor", "immutable data (in hdfs)", "in-memory computing", "in-memory database", 
    "incremental extraction", "insert only approach", "instance-level data quality problems", 
    "integrity constraints", "internal data resources", "internet data authenticity and quality", 
    "intra-query fault tolerance", "iot data", "iot data collection", "it progress", 
    "item-based filtering", "item-item matrix", "k-means clustering", "k-nearest neighbor", 
    "keras api", "kettle", "key-value database", "latent factors", "linear regression", 
    "log comparison (cdc)", "logical data model", "lossless compression", "lossy compression", 
    "low value density", "machine learning", "machine learning algorithms", "mapreduce", 
    "mapreduce batch processing model", "mapreduce computing engine", 
    "massively parallel processing (mpp)", "master node", "master-slave", "materialized aggregations", 
    "matrix factorization", "micro-batch stream processing system", "mirror scheme", 
    "missing data processing", "mixed structure", "ml persistence", "ml pipelines", 
    "mllib (machine learning library)", "model-level data quality problems", "multiple data sources", 
    "naive bayes algorithm", "name node", "naming conflict", "network big data", "networkx", 
    "new model of generating/consuming data", "nimbus", "nodes and edges", "noisy data processing", 
    "nosql database", "odbc (open database connectivity)", "olap", "old model of generating/consuming data", 
    "oltp", "opic", "orm (object/relation mapping)", "pagerank", "paradigm", "parameter tuning", 
    "paramgridbuilder", "partition tolerance (p)", "partitioning", "pattern matching", 
    "peer to peer", "perception stage", "persistence", "physical data model", "pipeline", 
    "principal component analysis (pca)", "projection", "quasi-structured data", 
    "query interface recognition", "rdd (resilient distributed dataset)", "rdd action", 
    "rdd transformation", "real-time analytics", "recommendation system", "regression algorithm", 
    "reinforcement learning", "relational database (rdbms)", 
    "remove gradually backward attributes subset selection", "repeat record cleaning", 
    "row-based store", "rtap", "s4 (simple, scalable streaming system)", "savedmodel", 
    "second paradigm of scientific research", "secondary name node", "seed url", 
    "segment/slave node", "self-operated data", "semi-structured data", "semi-supervised learning", 
    "shared-nothing architecture", "single data source", "singular value decomposition (svd)", 
    "six degrees of separation", "slot", "smoothing methods (binning, clustering, regression)", 
    "social network", "social network analysis (sna)", "soft-state", "spark", "spark architecture", 
    "spark sql", "spark streaming", "spout", "star-schema", "state passing model", 
    "step forward attributes subset selection", "storm", "stream processing", "strong consistency", 
    "structural conflict", "structured data", "superstep", "supervised learning", "supervisor", 
    "support vector machine", "surface web", "tensor", "tensorflow", "tensorflow processing unit (tpu)", 
    "tf.function", "third paradigm human-computer role", "third paradigm of scientific research", 
    "timestamp method", "topology", "tor (the onion router)", "transaction systems stage", 
    "transformer", "triggers method", "udal (unified data access layer)", 
    "unified data access interface (udai)", "unstructured data", "unsupervised learning", 
    "user profile", "user-based filtering", "user-generated content stage", 
    "user-user similarity matrix", "value", "variational autoencoder", "variety", "velocity", 
    "veracity", "virtualization technology", "volume", "waf (web application firewall)", 
    "weak consistency", "web crawler", "web crawler crawling process", "write pipeline (hdfs)"
]

# Normalize for comparison (lowercase)
before_normalized = {c.lower().strip(): c for c in before}
after_normalized = {c.lower().strip(): c for c in after}

# Find removed concepts
removed = set(before_normalized.keys()) - set(after_normalized.keys())

# Find added concepts (should be none if only merging)
added = set(after_normalized.keys()) - set(before_normalized.keys())

# Find modified concepts (same base but different casing/variation)
modified = []
for key in set(before_normalized.keys()) & set(after_normalized.keys()):
    if before_normalized[key] != after_normalized[key]:
        modified.append((before_normalized[key], after_normalized[key]))

print("=" * 80)
print("CONCEPT MERGE ANALYSIS")
print("=" * 80)
print(f"\nBefore: {len(before)} concepts")
print(f"After:  {len(after)} concepts")
print(f"Removed/Merged: {len(removed)} concepts")
print(f"Added: {len(added)} concepts")
print(f"Modified: {len(modified)} concepts")

if removed:
    print("\n" + "=" * 80)
    print("REMOVED/MERGED CONCEPTS:")
    print("=" * 80)
    for i, concept in enumerate(sorted(removed), 1):
        print(f"{i:3d}. {before_normalized[concept]}")

if modified:
    print("\n" + "=" * 80)
    print("MODIFIED CONCEPTS (name changes):")
    print("=" * 80)
    for i, (old, new) in enumerate(modified, 1):
        print(f"{i:3d}. '{old}' → '{new}'")

if added:
    print("\n" + "=" * 80)
    print("ADDED CONCEPTS (unexpected):")
    print("=" * 80)
    for i, concept in enumerate(sorted(added), 1):
        print(f"{i:3d}. {after_normalized[concept]}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"✅ Yes, {len(removed)} concepts were merged/removed")
if modified:
    print(f"📝 {len(modified)} concepts had name modifications")
print("=" * 80)

