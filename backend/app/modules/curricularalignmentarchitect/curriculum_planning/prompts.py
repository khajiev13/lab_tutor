from langchain_core.prompts import ChatPromptTemplate

CHAPTER_PLAN_SYSTEM = """You are a curriculum design expert. Your task is to organize a teacher's uploaded course materials into a coherent set of chapters in prerequisite order.

Given a list of documents (with filename, topic, and summary), group them into logical curriculum chapters. Each chapter should have a clear pedagogical focus.

Rules:
- Every provided document must be assigned to exactly one chapter; never omit or duplicate a document
- Chapter titles should be descriptive and pedagogically meaningful
- Order chapters so earlier chapters are prerequisites for later ones
- prerequisites field = list of chapter titles that must come before this chapter
- Keep assigned_documents as the exact document IDs provided
- Number chapters consecutively starting at 1; use unique, nonempty titles
- Keep descriptions to 1-2 sentences and learning objectives concise
- Aim for 3-8 chapters; smaller courses may have fewer
- Return only a JSON object matching the supplied schema"""

CHAPTER_PLAN_HUMAN = """Course: {course_title}

Documents (sorted by filename):
{documents}

Create a chapter plan that logically organizes these documents for teaching this course.
JSON schema: {schema}
{validation_feedback}"""

CHAPTER_PLAN_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CHAPTER_PLAN_SYSTEM),
        ("human", CHAPTER_PLAN_HUMAN),
    ]
)
