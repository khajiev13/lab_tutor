论证提出课题研究的总体思路，拟开展的主要研究内容及内涵，说明各部分研究内容之间的相关关系。
(中文宋体/英文Timies New Roman,小四、行间距22磅、段后0.5行)

1.1	Overall Research Idea

The core idea of this research is to design, build, and evaluate an AI Agentic Personalized learning platform that will create students’ personalized learning experience. The proposed system is a closed loop, agentic architecture designed to Trace, Diagnose, and Guide (TDG) students’ learning journey throughout classes. The entire system takes a Knowledge Graph (KG) as it is foundation, which will serve as the centeral “memory” and “conent architect”.[2]
i)	Foundation (KG): The KG will be a graph database built in neo4j, which will define the pre-requisit relationships between all course concepts, topics, and learning materials (such as, assessments, assignments, quizess, …etc). It will also serve as dynamic students’ model, storing rich performance data interactions and their diagnosed mastery levels based on concept and skill level. 
ii)	Frontend and Interaction: The student interacts with a JavaScript-based (e.g React) frontend dashboard and an integrated lab enviornment (e.g Jupyter lab) for coding practices with an interactive chatbot to assist the students.
iii)	The Loop (Dataflow): The system operates via a continuous feedback loop: 

<Insert Figure> 
•	Trace: All students actions (code, quiz answers, chat interaction,…etc) will be logged. The SQ-MLFBK-KT model is built with Hugging Face transformer and Pytorch) acting as the “Temporal Sensor”. 
•	Enrich and Diagnose: This data will enrich the student’s KG. The G-CDM-AD module, which is build with Pytorch Geometric will act as the “Structural Interpreter”. 
•	Guide (Decision Making): The unified outputs will serve as the “state” (s) for the Recommendation Learning (RL) Agent.[11] It is policy will be the “Decision-Making Brain”. 
•	Action(Generation and Recommendation): The agent’s actions is composed with two steps: 
1)	Generate: Use an LLM as a tool to generate personalized problems and hints. 
2)	Feedback: The student’s response is then captured, a reward (r) is calculated [28], the agent policy is updated, and the loop repeats.
Below is a table showing the problems addressed in this research, justifying the use of each technique. 
Problem	Solution (Objective)	Method (Specialized Technology)
Problem: How to capture a student's momentary knowledge state from sequential, multimodal interactions (code, NL questions)?	Solution: Trace (Temporal Sensing)	Method: SQ-MLFBK-KT (BERT-based Transformer)
Problem: How to interpret a student's entire history to build a stable, persistent, explainable map of their conceptual mastery?	Solution: Diagnose (Structural Interpretation)	Method: G-CDM-AD (Graph Neural Network)
Problem: How to use the student's current state (from Trace + Diagnose) to select the optimal next action (content or generation)?	Solution: Guide (Decision-Making)	Method: Reinforcement Learning (RL) Agent
Problem: How to handle new students with no interaction history (the "cold-start" problem) in Cognitive Diagnosis?	Solution: Provide Zero-Shot Initial Diagnosis	Method: Large Language Model (LLM) (via Initial Assessment Analysis)
Problem: How to generate novel problems, hints, and explanations that are perfectly tailored to the student's diagnosed gaps?	Solution: Generate Personalized Content	Method: Large Language Model (LLM) (as a "tool" used by the RL Agent)
Problem: How to store and connect all data (content, concepts, student mastery, interactions) in a unified, queryable structure?	Solution: Centralized Memory & Representation	Method: Dynamic Knowledge Graph (KG)

1.2	Embodiment of Innovation
The innovation of this project lays within the combination of different methods to create a robust system, having an integrated multiple state of the art technologies combined to one. 
1.2.1	Core Innovation: 
Methadolical Innovation: The Diagnostic-Generative Loop. This is the creation of a feedback loop between the KT and CD models, medited with the KG. This architecture solve the fundemental problem of the trade-off between predictive accuracy and explainability. 
Technological Innovation: The Agentic Recommendation Engine. This research moves beyond traditional recommendation models by implementing an autonomuos AI agent. This agent will be using “policy” as it is method to make decisions (the Solution) with the support of generative LLM as a tool to creat a tailored content on demand. 
Application Innovation: the coupling of project labs with our diagnostic models OKT for code and SQKT for questions allows the system to assess students perfomance authenticity, providing richer and valid signals towards students capabilities. 
1.3	Inter-Layer Relationships and logical Progression
To illustrate the complete “Diagnostic-Generative Loop” in practice, consider the following scenarios: 
1)	Trace: (SQ-MLFBK-KT): Innitially the student takes an initial assessment where we will capture the first student level, then based on that we will flag student’s confusion. SQ-MLFBK-KT will also aid with the student performace throughout the class. 
2)	Enrich the KG: this interaction is to log in the student’s new data as he progresses in the class. 
3)	Diagnose (G-CDM-AD): re-analyzed the enriched data, updating the student’s mastery profile.
4)	Guide (RL Agent): This updated mastery profile will be our new states (s) for the RL agent. 
5)	Action (Generate): The agent selects the suitable LLM tool. It performs KG-RAG- style query and generates a grounded prompt. 
6)	Action: A student submits failed query for an exercise . Then he uses the chat to ask a question, which will be linked to his account ID in the KG. 
7)	Loop: The student will go through this loop over and over, and everytime his portofolio updates and content is personalizedd based on his level. Their sucessful completion is captured with a positive reward (r) is generated, the policy is strengthen and the loop continue. 

<Insert figure>  
