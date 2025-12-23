# Quiz Generation Dataset Report

**Generated:** 2025-11-19 04:58:55

---

## Executive Summary

This report documents the generation of a graph-anchored quiz question dataset for pre-assessment purposes. The system generated **758 questions** from **253 theory-concept pairs**, covering **221 unique concepts** across **35 theories**.

### Key Metrics

- **Total Questions Generated:** 758
- **Total Questions Stored:** 757
- **Storage Success Rate:** 99.9%
- **Unique Concepts Covered:** 221
- **Theory-Concept Pairs Processed:** 253
- **Concepts with Multiple Theories:** 23
- **Average Questions per Concept:** 3.43

---

## 1. Graph-Anchored Question Dataset Properties

### Dataset Structure

The quiz questions are stored as `QUIZ_QUESTION` nodes in Neo4j, with explicit relationships to both `CONCEPT` and `TEACHER_UPLOADED_DOCUMENT` nodes. This dual-anchoring enables traceability and supports personalized question selection based on learning context.

### Graph Connectivity

- **Total Questions in Database:** 766
- **Questions Linked to CONCEPT Nodes:** 758
- **Questions Linked to TEACHER_UPLOADED_DOCUMENT Nodes:** 757
- **Fully Linked Questions (CONCEPT ↔ QUIZ_QUESTION ↔ TEACHER_UPLOADED_DOCUMENT):** 757
- **Questions with Text Evidence:** 766
- **Unique Concepts with Questions:** 221
- **Unique Theories with Questions:** 35

### Graph Structure Description

The knowledge graph structure follows this pattern:

```
CONCEPT --[HAS_QUESTION]--> QUIZ_QUESTION <--[HAS_QUESTION]-- TEACHER_UPLOADED_DOCUMENT
```

Each `QUIZ_QUESTION` node contains:
- `question_text`: The question prompt
- `option_a`, `option_b`, `option_c`, `option_d`: Multiple choice options
- `correct_answer`: The correct option (A, B, C, or D)
- `concept_name`: Name of the associated concept
- `theory_name`: Name of the associated theory
- `theory_id`: Unique identifier of the theory
- `text_evidence`: Source text excerpt used for question generation

This structure enables:
1. **Traceability:** Questions can be traced back to their source theory and concept
2. **Personalization:** Questions can be filtered by concept or theory for adaptive learning
3. **Explainability:** Text evidence provides context for why questions were generated

---

## 2. Generation Statistics

### Coverage Metrics

- **Total Theory-Concept Pairs:** 253
- **Pairs Successfully Processed:** 253
- **Processing Success Rate:** 100.0%
- **Questions Generated:** 758
- **Questions Stored:** 757
- **Storage Success Rate:** 99.9%

### Concept Coverage

- **Unique Concepts:** 221
- **Concepts with Multiple Theories:** 23

#### Concepts with Multiple Theories

The following concepts appear in multiple theories, demonstrating the system's ability to generate context-specific questions for the same concept across different theoretical frameworks:

- **computing platform and engine** (2 theories): Data Processing System Architecture, Distributed Graph Computing
- **data** (2 theories): Batch Processing with MapReduce, Data Processing System Architecture
- **data integration** (2 theories): Data Integration and Data Transformation, Data Preprocessing Techniques
- **data mining** (3 theories): Big Data Processing Algorithms: Machine Learning and Data Mining, Data Processing System Architecture, Popular Data Analysis Algorithms
- **data reduction** (2 theories): Data Preprocessing Techniques, Data Reduction Techniques
- **dimensionality reduction** (2 theories): Data Preprocessing Techniques, Data Reduction Techniques
- **etl (extract, transform, and load)** (4 theories): Big Data Lifecycle, Processing, and Business Intelligence Evolution, Big Data Processing Flow: Analytical and Technical Perspectives, Data Modeling in Data Storing Systems, Internal Data Acquisition using ETL
- **hadoop** (2 theories): Big Data General Architecture, Big Data Processing Flow: Analytical and Technical Perspectives
- **hdfs (hadoop distributed file system)** (3 theories): Batch Processing with MapReduce, Big Data Lifecycle, Processing, and Business Intelligence Evolution, Distributed File Systems and HDFS Architecture
- **in-memory** (3 theories): Data Processing System Architecture, In-Memory Computing with Spark, In-Memory Database: HANA Architecture and Technologies

*... and 13 more concepts with multiple theories*

### Questions per Concept Distribution

The system generates 3 questions per theory-concept pair. Concepts that appear in multiple theories will have more questions:

| Concept | Question Count |
|---------|----------------|
| etl (extract, transform, and load) | 12 |
| mapreduce | 12 |
| data mining | 9 |
| hdfs (hadoop distributed file system) | 9 |
| in-memory | 9 |
| machine learning | 9 |
| massively parallel processing (mpp) | 9 |
| computing platform and engine | 6 |
| data | 6 |
| data integration | 6 |
| data reduction | 6 |
| dimensionality reduction | 6 |
| hadoop | 6 |
| odbc-open database connectivity | 6 |
| olap: online analytical | 6 |
| oltp: online transaction | 6 |
| principal component analysis (pca) | 6 |
| reinforcement learning(rl) | 6 |
| shared nothing | 6 |
| spark mllib | 6 |

*... and 201 more concepts*

### Text Evidence Statistics

All questions are generated from text evidence extracted from source documents:

- **Average Text Evidence Length:** 154 characters
- **Minimum Length:** 26 characters
- **Maximum Length:** 465 characters

### Processing Performance

- **Average Time per Pair:** 37.39 seconds
- **Total Processing Time:** 9459.5 seconds

### Errors Encountered

**Total Errors:** 1

Sample errors:

- Failed to store question for 'transformers' (theory: Spark MLlib Concepts and Mechanisms)

---

## 3. Qualitative Properties

### Question Quality and Diversity

The generated questions demonstrate several qualitative properties:

1. **Text Evidence Alignment:** Questions are directly generated from source text evidence, ensuring relevance and accuracy
2. **Distractor Quality:** Incorrect options are designed to be plausible but clearly distinguishable from the correct answer
3. **Question Diversity:** Each theory-concept pair generates 3 unique questions, covering different facets of the concept
4. **Context Preservation:** Questions maintain links to their source theory and concept, enabling explainability

### Sample Questions

The following sample questions demonstrate the quality and structure of the generated dataset:

#### Sample Question 1

**Question:** In Principal Component Analysis (PCA), which of the following best describes the relationship between the number of original dimensions and the compressed data space?
- **A:** The number of compressed dimensions is always equal to the number of original dimensions.
- **B:** The number of compressed dimensions is less than or equal to the number of original dimensions.
- **C:** The number of compressed dimensions is independent of the number of original dimensions.
- **D:** The number of compressed dimensions is greater than the number of original dimensions.
- **Correct Answer:** B
- **Concept:** principal component analysis (pca)
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Principal component analysis (PCA) assumes that the data to be compressed consists of N tuples or data vectors taken from k dimensions. Principal component analysis and search to obtain c “k-dimension...

#### Sample Question 2

**Question:** In Principal Component Analysis (PCA), how does the dimensionality reduction process occur?
- **A:** By selecting a subset of the original data points that best represent the overall dataset.
- **B:** By projecting the data onto a set of orthogonal vectors that represent the most significant variance in the data.
- **C:** By using random vectors to approximate the underlying structure of the data.
- **D:** By applying a linear transformation to reduce the number of data points while retaining the original dimensionality.
- **Correct Answer:** B
- **Concept:** principal component analysis (pca)
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Principal component analysis (PCA) assumes that the data to be compressed consists of N tuples or data vectors taken from k dimensions. Principal component analysis and search to obtain c “k-dimension...

#### Sample Question 3

**Question:** In Principal Component Analysis (PCA), what is the primary goal when transforming the original data?
- **A:** To reduce the number of dimensions while maintaining as much of the original data's variance as possible
- **B:** To increase the number of dimensions for better data representation
- **C:** To normalize the data so that all dimensions are of equal importance
- **D:** To remove all correlations between the dimensions of the data
- **Correct Answer:** A
- **Concept:** principal component analysis (pca)
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Principal component analysis (PCA) assumes that the data to be compressed consists of N tuples or data vectors taken from k dimensions. Principal component analysis and search to obtain c “k-dimension...

#### Sample Question 4

**Question:** Which of the following is a key feature of numerosity reduction in data management?
- **A:** Using larger data units to represent information more accurately
- **B:** Applying data models to compress and represent data with fewer resources
- **C:** Increasing the size of data sets to improve model precision
- **D:** Requiring more detailed data for enhanced accuracy and analysis
- **Correct Answer:** B
- **Concept:** numerosity reduction
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Numerosity reduction -use smaller data to represent data, or use shorter data units, or use data models to represent data to reduce the amount of data.

#### Sample Question 5

**Question:** Which of the following techniques is primarily used to reduce the amount of data in numerosity reduction?
- **A:** Increasing the data size for better precision
- **B:** Using data models or shorter data units to represent data
- **C:** Storing data in more detailed formats for accuracy
- **D:** Applying data encryption for security purposes
- **Correct Answer:** B
- **Concept:** numerosity reduction
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Numerosity reduction -use smaller data to represent data, or use shorter data units, or use data models to represent data to reduce the amount of data.

#### Sample Question 6

**Question:** Which of the following best describes the concept of numerosity reduction?
- **A:** It involves using larger data units to represent more complex datasets.
- **B:** It refers to the process of using smaller data, shorter data units, or data models to reduce the amount of data.
- **C:** It focuses on increasing data size to improve data accuracy.
- **D:** It requires using uncompressed data to maintain the integrity of the original dataset.
- **Correct Answer:** B
- **Concept:** numerosity reduction
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Numerosity reduction -use smaller data to represent data, or use shorter data units, or use data models to represent data to reduce the amount of data.

#### Sample Question 7

**Question:** What is the primary consequence of using lossy compression on data?
- **A:** The original data can be perfectly restored without any loss of quality.
- **B:** The compressed data will be identical to the original data.
- **C:** Only an approximate version of the original data can be reconstructed.
- **D:** Lossy compression has no effect on the data's quality or accuracy.
- **Correct Answer:** C
- **Concept:** lossy compression
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Lossy compression: Only an approximate representation of the original data can be reconstructed.

#### Sample Question 8

**Question:** What is a key characteristic of lossy compression when compared to lossless compression?
- **A:** Lossy compression allows for the perfect reconstruction of the original data.
- **B:** Lossy compression results in the loss of some data, leading to an approximate reconstruction.
- **C:** Lossy compression requires no data loss during the process of compression and decompression.
- **D:** Lossy compression maintains all the details of the original data without any approximation.
- **Correct Answer:** B
- **Concept:** lossy compression
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Lossy compression: Only an approximate representation of the original data can be reconstructed.

#### Sample Question 9

**Question:** Which of the following best describes lossy compression?
- **A:** It reconstructs the original data exactly as it was before compression.
- **B:** It creates a lossless representation that can be reconstructed without any changes.
- **C:** It reconstructs only an approximate representation of the original data.
- **D:** It compresses data by removing all unnecessary bits without altering the original information.
- **Correct Answer:** C
- **Concept:** lossy compression
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Lossy compression: Only an approximate representation of the original data can be reconstructed.

#### Sample Question 10

**Question:** Which of the following accurately describes the result of using lossless compression on data?
- **A:** The original data is permanently altered to reduce file size.
- **B:** The compressed data can be fully restored without any loss of information.
- **C:** Data loss occurs during compression, but the compressed file is smaller.
- **D:** The compressed data is easier to access but cannot be restored to its original form.
- **Correct Answer:** B
- **Concept:** lossless compression
- **Theory:** Data Reduction Techniques
- **Text Evidence Excerpt:** Lossless compression: Compressed data can be restored without losing any information.

*... and 10 more sample questions*

---

## 4. System Capabilities & Insights

### Pre-Assessment Question Bank

The generated dataset serves as a comprehensive pre-assessment question bank with the following properties:

1. **Comprehensive Coverage:** Questions cover all concepts across all theories in the knowledge base
2. **Scalable Generation:** The system can generate questions for new concepts as they are added to the knowledge graph
3. **Quality Assurance:** Each question is validated for uniqueness and stored with full traceability

### Traceability and Explainability

Every question in the dataset maintains explicit links to:

- **Source Concept:** The concept being assessed
- **Source Theory:** The theoretical context from which the question was generated
- **Text Evidence:** The specific text excerpt used for question generation

This traceability enables:

- **Explainability:** Students can see why a question was asked and what it assesses
- **Debugging:** Incorrect questions can be traced back to their source
- **Quality Control:** Questions can be reviewed in context of their source material

### Personalization Potential

The graph-anchored structure enables several personalization strategies:

1. **Concept-Based Selection:** Questions can be filtered by specific concepts a student needs to practice
2. **Theory-Based Selection:** Questions can be selected from specific theories based on learning path
3. **Multi-Theory Concepts:** For concepts appearing in multiple theories, questions can be selected to show different perspectives
4. **Adaptive Difficulty:** Questions can be weighted based on concept complexity or theory depth

### Multi-Theory Concept Handling

The system identified **23 concepts** that appear in multiple theories. For these concepts, the system generates separate question sets for each theory-concept pair, allowing for context-specific assessment. This demonstrates the system's ability to handle concepts that have different interpretations or applications across different theoretical frameworks.

#### Example Multi-Theory Concept

**Concept:** computing platform and engine
**Appears in 2 theories:**

- Data Processing System Architecture
- Distributed Graph Computing

This concept receives separate question sets for each theory, ensuring that questions are contextually appropriate to the specific theoretical framework.

---

## Appendix: Detailed Statistics

### Questions per Theory Distribution

| Theory | Question Count |
|--------|----------------|
| NoSQL Databases: CAP Theorem and BASE Transaction Model | 39 |
| TensorFlow Concepts, Mechanism, and TensorFlow 2.0 | 36 |
| Data Reduction Techniques | 30 |
| Massively Parallel Processing (MPP) for Structured Data | 27 |
| Data Integration and Data Transformation | 27 |
| Internal Data Acquisition using ETL | 27 |
| Stream Computing Model and Storm Framework | 27 |
| Spark MLlib Concepts and Mechanisms | 26 |
| Big Data Lifecycle, Processing, and Business Intelligence Evolution | 26 |
| Recommendation Systems: Collaborative, Content-Based, and Knowledge-Based Filtering | 24 |
| Popular Data Analysis Algorithms | 24 |
| Data Processing System Architecture | 24 |
| Batch Processing with MapReduce | 24 |
| Social Network Analysis | 24 |
| Data Cleaning Techniques | 24 |
| In-Memory Computing with Spark | 24 |
| Big Data General Architecture | 24 |
| In-Memory Database: HANA Architecture and Technologies | 21 |
| Distributed Graph Computing | 21 |
| Data Preprocessing Techniques | 21 |
| Data Modeling in Data Storing Systems | 21 |
| NoSQL Database Types | 18 |
| Unified Data Access Interface | 18 |
| Distributed File Systems and HDFS Architecture | 18 |
| Big Data Characteristics: The 5Vs | 18 |
| Big Data Processing Algorithms: Machine Learning and Data Mining | 18 |
| Big Data Processing Flow: Analytical and Technical Perspectives | 15 |
| Deep Web Data Acquisition | 15 |
| Four Main Types of NoSQL Databases | 15 |
| Introduction to NoSQL Databases | 15 |

*... and 5 more theories*

### Neo4j Query Examples

To explore the dataset in Neo4j Browser:

```cypher
// Get all questions for a concept
MATCH (c:CONCEPT {name: 'YourConcept'})-[:HAS_QUESTION]->(q:QUIZ_QUESTION)
RETURN q

// Get questions from a specific theory
MATCH (t:TEACHER_UPLOADED_DOCUMENT {id: 'theory_id'})-[:HAS_QUESTION]->(q:QUIZ_QUESTION)
RETURN q

// Get questions with full context
MATCH (c:CONCEPT)-[:HAS_QUESTION]->(q:QUIZ_QUESTION)<-[:HAS_QUESTION]-(t:TEACHER_UPLOADED_DOCUMENT)
RETURN c.name, q.question_text, t.name
LIMIT 25
```

---

*Report generated on 2025-11-19 04:58:55*
