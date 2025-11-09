
# Dynamic Lab and Theory Generation System

## Overview

This document outlines the architecture for a dynamic system that generates both personalized theoretical content and practical labs for students. A **single orchestrator agent** coordinates the entire process, ensuring that both theoretical and practical components are delivered in a balanced and personalized manner.

## System Components

### 1. Orchestrator Agent
- **Purpose:** Acts as the central coordinator, determining when to generate theoretical content, practical labs, or both, based on the student's needs and the context.
- **Responsibilities:**
  - **Receive Input:** Accepts the student’s metadata (e.g., level, hobbies) and class context (e.g., theory name, concepts).
  - **Contextual Analysis:** Decides which components (theory, practical, or both) are needed based on the course objectives and the student’s profile.
  - **Generate and Sequence:** Coordinates the generation of both theory and practical labs, ensuring a logical progression from theory to hands-on application. The orchestrator can determine if the student should engage with theoretical content first, or whether a practical lab should precede the theory for better engagement.
  - **Delivery Coordination:** Ensures smooth delivery of both content types, either simultaneously or in a planned sequence, while adjusting the complexity to match the student's level.

### 2. Theory Generation Agent
- **Purpose:** Curates and delivers the theoretical learning content to the student.
- **Responsibilities:**
  - **Content Generation:** Fetches relevant theoretical resources (e.g., articles, summaries, or explanations) based on the topics covered in class.
  - **Interactive Prompts:** Provides quizzes, reflection questions, and interactive discussions to ensure comprehension.
  - **Adaptive Learning:** Adjusts content depth and complexity according to the student’s level, reinforcing prior concepts and expanding on more complex topics.

### 3. Lab Generation Agent
- **Purpose:** Creates hands-on practical labs for students to apply theoretical knowledge.
- **Responsibilities:**
  - **Dataset Creation:** Generates datasets in formats such as CSV or JSON, aligned with the theoretical concepts covered.
  - **Code Generation:** Produces step-by-step code for the lab, with accompanying explanations and instructional hints.
  - **Lab Personalization:** Adjusts the lab complexity based on the student’s level, ensuring it is appropriately challenging, whether the student is a beginner or advanced learner.
  - **Execution Flow:** Allows students to execute the lab in stages, providing real-time feedback and hints as necessary.

## Workflow Summary

1. **Orchestrator Input:** The orchestrator receives the student's metadata and class context.
2. **Decision Point:** The orchestrator determines if both theoretical and practical content should be generated.
    - If **both** are required, the orchestrator:
      1. First routes the task to the **Theory Generation Agent** to prepare the theoretical content.
      2. After the theory is delivered, the orchestrator passes the task to the **Lab Generation Agent** to create the practical lab.
    - If only **theoretical** content is required, the orchestrator sends the request to the **Theory Generation Agent**.
    - If only **practical** content is needed, the orchestrator sends the request to the **Lab Generation Agent**.
3. **Content Delivery:** Both theoretical content and practical labs are delivered to the student in sequence (or simultaneously, if preferred) based on the orchestrator's analysis and the student’s learning path.
4. **Feedback Loop:** The orchestrator gathers feedback from the student as they progress through both the theoretical and practical parts, adjusting future content to enhance learning outcomes.

## Goal

The goal is to provide a dynamic, personalized learning experience where both theoretical understanding and practical application are integrated into the student's learning journey. The orchestrator ensures that the student receives the right mix of content at the right time, promoting deeper comprehension and skill-building.
