"""Prompt templates for technical document concept extraction.

Ported from `knowledge_graph_builder/prompts/extraction_prompts.py` for backend runtime.
"""

# System instruction for the extraction task
SYSTEM_INSTRUCTION = """You are an expert at analyzing technical and educational lecture transcripts to extract structured knowledge.

**Task**: Extract the following four categories of information from the text:
1. **Topic Title (TOPIC)**: A single concise title summarizing the session's overall subject.
2. **Compressed Summary (SUMMARY)**: A clear and coherent summary of the session, reduced to 30–50% of the original length, covering all major sections and arguments.
3. **Keywords (KEYWORDS)**: A list of 5–10 high-value terms, phrases, or entities most central to the lecture.
4. **Concepts (CONCEPT)**: All important theories, models, technologies, frameworks, or technical terms. For each, provide a `definition` using the text's exact meaning (avoid paraphrasing unless clarification is necessary) and `text_evidence` as a verbatim quote.

**Extraction Rules**:
- Extract exactly one TOPIC.
- Extract exactly one SUMMARY that maintains logical flow.
- Extract 5–10 KEYWORDS.
- Extract multiple CONCEPT entities.
- Preserve specificity: keep technical names, acronyms, and terminology intact (e.g., "MapReduce," "ODBC," "DIKW pyramid").

**Quality Standards**:
- Only extract information explicitly mentioned in the source text
- Provide exact text evidence for each concept definition
- Use clear, descriptive concept names as they appear in the text
- Ensure all extracted information is directly supported by the source text
- Maintain technical accuracy and preserve domain-specific terminology"""

# Task instruction template
TASK_INSTRUCTION = """Analyze the following technical document and extract structured knowledge according to the specified format.

**Source Text:**
{text}

**Required Output JSON Format:**
{{
  "topic": "...",
  "summary": "...",
  "keywords": ["...", "..."],
  "concepts": [
    {{
      "name": "...",
      "definition": "...",
      "text_evidence": "..."
    }}
  ]
}}

Ensure all extractions are grounded in the source text and maintain technical precision."""

# Complete prompt template combining system and task instructions
COMPLETE_EXTRACTION_PROMPT = f"""{SYSTEM_INSTRUCTION}

{TASK_INSTRUCTION}"""

# Few-shot examples for better model performance
EXTRACTION_EXAMPLES = """
**Example Input:**
"The Big Data lifecycle has four stages: Collect, Store, Analyze, and Governance. Collecting involves gathering structured and unstructured data. Storage relies on platforms like HDFS and databases. Analysis applies tools like MapReduce, Spark, and MySQL. Governance ensures compliance, accuracy, and security. The DIKW pyramid explains the transformation from data to information, knowledge, and wisdom."

**Example Output:**
{{
  "topic": "Big Data Lifecycle and Analysis Frameworks",
  "summary": "The Big Data lifecycle consists of four stages: collection, storage, analysis, and governance. Collection gathers structured and unstructured data. Storage uses HDFS, MySQL, and databases. Analysis employs MapReduce and Spark for large-scale processing. Governance ensures compliance and data quality. The DIKW pyramid illustrates the progression from raw data to actionable wisdom.",
  "keywords": ["big data lifecycle", "collect", "store", "analyze", "governance", "DIKW pyramid", "Hadoop", "Spark", "HDFS", "MapReduce"],
  "concepts": [
    {{
      "name": "DIKW Pyramid",
      "definition": "A model showing the progression from data (facts) to information (organized data), to knowledge (meaningful information), and wisdom (actionable insights).",
      "text_evidence": "The DIKW pyramid explains the transformation from data to information, knowledge, and wisdom."
    }},
    {{
      "name": "HDFS",
      "definition": "Hadoop Distributed File System, the main storage platform for big data, supporting distributed processing.",
      "text_evidence": "Storage relies on platforms like HDFS and databases."
    }},
    {{
      "name": "MapReduce",
      "definition": "A programming model for processing large data sets with a distributed algorithm on a cluster.",
      "text_evidence": "Analysis applies tools like MapReduce, Spark, and MySQL."
    }}
  ]
}}
"""

# Template with few-shot examples for improved performance
EXTRACTION_PROMPT_WITH_EXAMPLES = f"""{SYSTEM_INSTRUCTION}

**Example for Reference:**
{EXTRACTION_EXAMPLES}

{TASK_INSTRUCTION}"""
