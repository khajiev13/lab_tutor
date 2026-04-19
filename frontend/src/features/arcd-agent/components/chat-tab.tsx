
import { useState, useRef, useEffect, useCallback } from "react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MathText, MarkdownMath } from "@/features/arcd-agent/components/math-text";
import type { StudentPortfolio } from "@/features/arcd-agent/lib/types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

interface Progress {
  current: number;
  total: number;
  correct: number;
  score: number;
  max_score: number;
}

interface QuestionData {
  index: number;
  total: number;
  skill_name: string;
  difficulty: string;
  is_pco: boolean;
  question: string;
  hint: string;
}

interface FeedbackData {
  correct: boolean;
  message: string;
  explanation: string;
  correct_answer: string;
  skill_name: string;
  suggested_mastery_delta?: number;
}

interface SkillSummary {
  skill_name: string;
  total: number;
  correct: number;
  mastery_start: number;
  mastery_end: number;
  is_pco: boolean;
}

interface ResultItem {
  index: number;
  skill_name: string;
  question: string;
  correct_answer: string;
  student_answer: string;
  is_correct: boolean;
  mastery_delta: number;
  mastery_before: number;
  mastery_after: number;
  difficulty: string;
  is_pco: boolean;
  points: number;
  feedback_snippet: string;
}

interface ReviewSummaryData {
  score: number;
  max_score: number;
  correct_count: number;
  total_questions: number;
  percentage: number;
  results: ResultItem[];
  skills_summary: SkillSummary[];
  strengths: string[];
  areas_for_improvement: string[];
  llm_feedback: string;
}

interface ChatEntry {
  type: "greeting" | "question" | "answer" | "feedback" | "complete" | "chat-user" | "chat-reply" | "system" | "summary";
  content: string;
  data?: QuestionData | FeedbackData | ReviewSummaryData | null;
}

interface ConversationSnapshot {
  id: string;
  createdAt: number;
  label: string;
  entries: ChatEntry[];
}

interface OpenConversationTab {
  id: string;
  label: string;
  entries: ChatEntry[];
}

interface ChatTabProps {
  student: StudentPortfolio;
  datasetId: string;
  practiceSkill?: { id: number; name: string } | null;
  onPracticeConsumed?: () => void;
  /** Called after every answer/skip to refresh the global portfolio data. */
  onDataChanged?: () => void;
}

export function ReviewChatTab({ student, datasetId, practiceSkill, onPracticeConsumed, onDataChanged }: ChatTabProps) {
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<QuestionData | null>(null);
  const [hints, setHints] = useState<string[]>([]);
  const [hintLoading, setHintLoading] = useState(false);
  const [hintsFinal, setHintsFinal] = useState(false);
  const [inputMode, setInputMode] = useState<"answer" | "ask">("answer");
  const [lastFeedback, setLastFeedback] = useState<FeedbackData | null>(null);
  const [reviewComplete, setReviewComplete] = useState(false);
  const [mode, setMode] = useState<"idle" | "review" | "chat">("idle");
  const [sessionType, setSessionType] = useState<"auto" | "manual" | null>(null);
  const [thinkingMode, setThinkingMode] = useState<"fast" | "deep">("fast");
  const [reviewOptions, setReviewOptions] = useState<{
    suggested_skills: string[];
    selected_skills: string[];
    mastery_map: Record<string, number>;
    question_count_bounds?: { min: number; max: number; default_fast: number; default_deep: number };
  } | null>(null);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [customSkill, setCustomSkill] = useState("");
  const [questionCount, setQuestionCount] = useState<number>(5);
  const [sessionAnalysis, setSessionAnalysis] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<ConversationSnapshot[]>([]);
  const [openHistoryTabs, setOpenHistoryTabs] = useState<OpenConversationTab[]>([]);
  const [activeHistoryTabId, setActiveHistoryTabId] = useState<string | null>(null);
  const [editingHistoryId, setEditingHistoryId] = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState("");
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const historyKey = `arcd_conversation_history_${datasetId}_${student.uid}`;

  const scrollToBottom = useCallback(() => {
    setTimeout(() => scrollRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }, []);

  useEffect(() => { scrollToBottom(); }, [entries, currentQuestion, lastFeedback, hints, scrollToBottom]);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`, { headers: authHeaders() })
      .then((r) => r.ok ? setConnected(true) : setConnected(false))
      .catch(() => setConnected(false));
  }, []);

  useEffect(() => {
    if (connected === false) return;
    fetch(`${API_BASE}/api/review/options`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ dataset_id: datasetId, student_uid: student.uid }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        setReviewOptions(data);
        const defaults = (data.suggested_skills?.length ? data.suggested_skills : data.selected_skills ?? []).slice(0, 6);
        setSelectedSkills(defaults);
      })
      .catch(() => {});
  }, [datasetId, student.uid, connected]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(historyKey);
      setConversationHistory(raw ? JSON.parse(raw) : []);
    } catch {
      setConversationHistory([]);
    }
    setOpenHistoryTabs([]);
    setActiveHistoryTabId(null);
  }, [historyKey]);

  useEffect(() => {
    setQuestionCount(thinkingMode === "deep" ? 9 : 5);
  }, [thinkingMode]);

  // Restore or reset state when student/dataset changes.
  // Restore is SYNCHRONOUS so the student never sees a flash of the welcome screen.
  useEffect(() => {
    const key = `arcd_review_${datasetId}_${student.uid}`;
    let restored = false;
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const saved = JSON.parse(raw);
        const age = Date.now() - (saved.savedAt ?? 0);
        if (age < 3600_000 && saved.sessionId && saved.mode !== "idle") {
          // Restore immediately — no waiting for server verification
          setSessionId(saved.sessionId);
          setEntries(saved.entries ?? []);
          setProgress(saved.progress ?? null);
          setCurrentQuestion(saved.currentQuestion ?? null);
          setLastFeedback(saved.lastFeedback ?? null);
          setReviewComplete(saved.reviewComplete ?? false);
          setMode(saved.mode ?? "review");
          setHints(saved.hints ?? []);
          setHintsFinal(saved.hintsFinal ?? false);
          setInputMode(saved.inputMode ?? "answer");
          restored = true;

          // Verify server session in background; if expired, notify but don't flash reset
          fetch(`${API_BASE}/api/review/session/${saved.sessionId}`, { headers: authHeaders() })
            .then((r) => r.ok ? r.json() : null)
            .then((data) => {
              if (!data?.alive || data.is_complete) {
                localStorage.removeItem(key);
                setEntries((prev) => [
                  ...prev,
                  {
                    type: "system",
                    content:
                      "Your previous review session is no longer active. You can start a new review anytime, and your saved conversation history is still available.",
                  },
                ]);
                setCurrentQuestion(null);
                setMode("review");
                setReviewComplete(true);
              } else if (!saved.currentQuestion && !saved.reviewComplete) {
                // Session alive but we lost the question (e.g. navigated during generation) — re-fetch it
                fetchNextQuestion(saved.sessionId);
              }
            })
            .catch(() => { /* keep restored state; will fail on next user action naturally */ });
        } else {
          localStorage.removeItem(key);
        }
      }
    } catch { /* ignore corrupt localStorage */ }
    if (!restored) resetState();
  }, [student.uid, datasetId]); // eslint-disable-line react-hooks/exhaustive-deps

  function resetState() {
    setEntries([]);
    setSessionId(null);
    setProgress(null);
    setCurrentQuestion(null);
    setLastFeedback(null);
    setReviewComplete(false);
    setMode("idle");
    setSessionType(null);
    setHints([]);
    setHintsFinal(false);
    setInputMode("answer");
    // Return to clean setup defaults so student can reconfigure next session
    setQuestionCount(thinkingMode === "deep" ? 9 : 5);
    if (reviewOptions) {
      const defaults = (reviewOptions.suggested_skills?.length ? reviewOptions.suggested_skills : reviewOptions.selected_skills ?? []).slice(0, 6);
      setSelectedSkills(defaults);
    }
  }

  const saveConversationSnapshot = useCallback((label: string) => {
    if (entries.length === 0) return;
    const snapshot: ConversationSnapshot = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      createdAt: Date.now(),
      label,
      entries: entries.slice(-120),
    };
    setConversationHistory((prev) => {
      const next = [snapshot, ...prev].slice(0, 15);
      try {
        localStorage.setItem(historyKey, JSON.stringify(next));
      } catch {
        // ignore quota errors
      }
      return next;
    });
  }, [entries, historyKey]);

  const renameHistorySnapshot = useCallback((id: string, label: string) => {
    const trimmed = label.trim();
    if (!trimmed) return;
    setConversationHistory((prev) => {
      const next = prev.map((item) => (item.id === id ? { ...item, label: trimmed } : item));
      try {
        localStorage.setItem(historyKey, JSON.stringify(next));
      } catch {
        // ignore quota errors
      }
      return next;
    });
  }, [historyKey]);

  const closeHistoryTab = useCallback((id: string) => {
    setOpenHistoryTabs((prev) => {
      const next = prev.filter((tab) => tab.id !== id);
      if (activeHistoryTabId === id) {
        setActiveHistoryTabId(next[0]?.id ?? null);
      }
      return next;
    });
  }, [activeHistoryTabId]);

  // Persist review state to localStorage on meaningful changes.
  // Skip saving during the initial render (before restore completes).
  const hasInitialized = useRef(false);
  useEffect(() => {
    if (!hasInitialized.current) { hasInitialized.current = true; return; }
    if (!sessionId || mode === "idle") return;
    const key = `arcd_review_${datasetId}_${student.uid}`;
    const state = {
      sessionId, entries, progress, currentQuestion, lastFeedback,
      hints, hintsFinal, mode, inputMode, reviewComplete, savedAt: Date.now(),
    };
    try { localStorage.setItem(key, JSON.stringify(state)); } catch { /* quota */ }
  }, [sessionId, entries, progress, currentQuestion, lastFeedback, hints, hintsFinal, mode, reviewComplete, datasetId, student.uid, inputMode]);

  // Save session summary when review completes (for Littlebird-style recall)
  useEffect(() => {
    if (!reviewComplete || !progress) return;
    const summaryKey = `arcd_last_session_${datasetId}_${student.uid}`;
    const skills = entries
      .filter((e) => e.type === "question" || (e.data && "skill_name" in e.data))
      .map((e) => (e.data as FeedbackData)?.skill_name)
      .filter(Boolean);
    const uniqueSkills = [...new Set(skills)];
    const summary = {
      date: new Date().toISOString(),
      correct: progress.correct,
      total: progress.total,
      score: progress.score,
      skills: uniqueSkills,
    };
    try { localStorage.setItem(summaryKey, JSON.stringify(summary)); } catch { /* quota */ }
    // Clear active session from localStorage
    localStorage.removeItem(`arcd_review_${datasetId}_${student.uid}`);
    saveConversationSnapshot("Completed review session");
    setAnalysisLoading(true);
    fetch(`${API_BASE}/api/review/analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ dataset_id: datasetId, session_summary: summary }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setSessionAnalysis(data?.analysis ?? null))
      .catch(() => setSessionAnalysis(null))
      .finally(() => setAnalysisLoading(false));
  }, [reviewComplete]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-start a practice session when navigating from Learning Path
  useEffect(() => {
    if (!practiceSkill || connected === false) return;
    const startPractice = async () => {
      setLoading(true);
      setMode("review");
      setLastFeedback(null);
      setReviewComplete(false);
      setHints([]);
      setHintsFinal(false);
      setInputMode("answer");
      try {
        const res = await fetch(`${API_BASE}/api/review/practice-skill`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            dataset_id: datasetId,
            student_uid: student.uid,
            skill_id: practiceSkill.id,
            n_questions: thinkingMode === "deep" ? 5 : 3,
            thinking_mode: thinkingMode,
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setSessionId(data.session_id);
        setProgress(data.progress);
        setEntries([{ type: "greeting", content: data.greeting }]);
        fetchNextQuestion(data.session_id);
      } catch (e) {
        setEntries([{
          type: "system",
          content: `Could not start practice session: ${e instanceof Error ? e.message : String(e)}`,
        }]);
        setMode("idle");
        setLoading(false);
      }
      onPracticeConsumed?.();
    };
    startPractice();
  }, [practiceSkill]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchNextQuestion = useCallback(async (sid: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/review/next-question`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ session_id: sid }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setCurrentQuestion(data.current_question);
      if (data.progress) setProgress(data.progress);
    } catch (e) {
      setEntries((prev) => [...prev, { type: "system", content: `Failed to load question: ${e instanceof Error ? e.message : String(e)}` }]);
    }
    setLoading(false);
  }, []);

  const startReview = useCallback(async () => {
    // Auto mode uses all model-suggested skills; manual mode uses student selection
    const skillsToUse = sessionType === "auto"
      ? (reviewOptions?.suggested_skills ?? selectedSkills)
      : selectedSkills;
    if (!skillsToUse.length) {
      setEntries([{ type: "system", content: "Please select at least one skill before starting review." }]);
      return;
    }
    setLoading(true);
    setMode("review");
    setLastFeedback(null);
    setReviewComplete(false);
    setHints([]);
    setHintsFinal(false);
    setInputMode("answer");
    try {
      const res = await fetch(`${API_BASE}/api/review/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          dataset_id: datasetId,
          student_uid: student.uid,
          max_questions: questionCount,
          thinking_mode: thinkingMode,
          selected_skills: skillsToUse,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessionId(data.session_id);
      setProgress(data.progress);
      setEntries([{ type: "greeting", content: data.greeting }]);

      if (data.current_question) {
        setCurrentQuestion(data.current_question);
        setLoading(false);
      } else {
        fetchNextQuestion(data.session_id);
      }
    } catch (e) {
      setEntries([{ type: "system", content: `Could not connect to server. Error: ${e instanceof Error ? e.message : String(e)}` }]);
      setMode("idle");
      setLoading(false);
    }
    inputRef.current?.focus();
  }, [datasetId, student.uid, thinkingMode, questionCount, selectedSkills, sessionType, reviewOptions, fetchNextQuestion]);

  const submitAnswer = useCallback(async () => {
    const text = input.trim();
    if (!text || loading || !sessionId) return;

    setEntries((prev) => [...prev, { type: "answer", content: text }]);
    setInput("");
    setLoading(true);
    setHints([]);
    setHintsFinal(false);

    try {
      const res = await fetch(`${API_BASE}/api/review/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ session_id: sessionId, answer: text }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      setProgress(data.progress);
      setLastFeedback(data.feedback);
      setEntries((prev) => [...prev, { type: "feedback", content: data.feedback.message, data: data.feedback }]);

      // Notify parent that portfolio data changed
      onDataChanged?.();

      if (data.is_complete) {
        setCurrentQuestion(null);
        setReviewComplete(true);
        if (data.completion_message) {
          setEntries((prev) => [...prev, { type: "complete", content: data.completion_message }]);
        }
        if (data.review_summary) {
          setEntries((prev) => [...prev, { type: "summary", content: "", data: data.review_summary }]);
          if (data.review_summary.needs_replan) {
            import("sonner").then(({ toast }) => {
              toast.info("Learning path updated", {
                description: "Your mastery changed enough to suggest a new plan. Visit Learning Path to regenerate.",
                duration: 6000,
              });
            });
          }
        }
      } else if (data.next_question) {
        setCurrentQuestion(data.next_question);
        setLastFeedback(null);
      }
    } catch (e) {
      setEntries((prev) => [...prev, { type: "system", content: `Error: ${e instanceof Error ? e.message : String(e)}` }]);
    }
    setLoading(false);
    inputRef.current?.focus();
  }, [input, loading, sessionId, onDataChanged]);

  const explainConcept = useCallback(async () => {
    if (loading || !sessionId) return;
    setLoading(true);
    setEntries((prev) => [...prev, { type: "chat-user", content: "Can you explain this concept?" }]);
    try {
      const res = await fetch(`${API_BASE}/api/review/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEntries((prev) => [...prev, { type: "chat-reply", content: data.explanation }]);
    } catch (e) {
      setEntries((prev) => [...prev, { type: "system", content: `Error: ${e instanceof Error ? e.message : String(e)}` }]);
    }
    setLoading(false);
    inputRef.current?.focus();
  }, [loading, sessionId]);

  const skipQuestion = useCallback(async () => {
    if (loading || !sessionId) return;
    setLoading(true);
    setHints([]);
    setHintsFinal(false);
    setEntries((prev) => [...prev, { type: "answer", content: "I'd like to skip this one." }]);
    try {
      const res = await fetch(`${API_BASE}/api/review/skip`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      setProgress(data.progress);
      setLastFeedback(data.feedback);
      setEntries((prev) => [...prev, { type: "feedback", content: data.feedback.message, data: data.feedback }]);

      // Notify parent that portfolio data changed
      onDataChanged?.();

      if (data.is_complete) {
        setCurrentQuestion(null);
        setReviewComplete(true);
        if (data.completion_message) {
          setEntries((prev) => [...prev, { type: "complete", content: data.completion_message }]);
        }
        if (data.review_summary) {
          setEntries((prev) => [...prev, { type: "summary", content: "", data: data.review_summary }]);
          if (data.review_summary.needs_replan) {
            import("sonner").then(({ toast }) => {
              toast.info("Learning path updated", {
                description: "Your mastery changed enough to suggest a new plan. Visit Learning Path to regenerate.",
                duration: 8000,
              });
            }).catch(() => {});
          }
        }
      } else if (data.next_question) {
        setCurrentQuestion(data.next_question);
        setLastFeedback(null);
      }
    } catch (e) {
      setEntries((prev) => [...prev, { type: "system", content: `Error: ${e instanceof Error ? e.message : String(e)}` }]);
    }
    setLoading(false);
    inputRef.current?.focus();
  }, [loading, sessionId, onDataChanged]);

  const fetchHint = useCallback(async () => {
    if (hintLoading || !sessionId || hintsFinal) return;
    setHintLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/review/hint`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ session_id: sessionId, answer: "" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setHints((prev) => [...prev, data.hint]);
      if (data.is_final_hint) setHintsFinal(true);
      scrollToBottom();
    } catch (e) {
      setEntries((prev) => [...prev, { type: "system", content: `Hint error: ${e instanceof Error ? e.message : String(e)}` }]);
    }
    setHintLoading(false);
  }, [hintLoading, sessionId, hintsFinal, scrollToBottom]);

  const askReviewQuestion = useCallback(async () => {
    const text = input.trim();
    if (!text || loading || !sessionId) return;

    setEntries((prev) => [...prev, { type: "chat-user", content: text }]);
    setInput("");
    setLoading(true);

    // Add streaming placeholder
    setEntries((prev) => [...prev, { type: "chat-reply", content: "" }]);

    try {
      const res = await fetch(`${API_BASE}/api/review/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          session_id: sessionId, message: text,
          thinking_mode: thinkingMode,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let fullReply = "";
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.token) {
              fullReply += data.token;
              setEntries((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { type: "chat-reply", content: fullReply };
                return updated;
              });
            }
          } catch { /* skip malformed SSE lines */ }
        }
      }
    } catch (e) {
      setEntries((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.type === "chat-reply" && !last.content) {
          updated[updated.length - 1] = { type: "system", content: `Error: ${e instanceof Error ? e.message : String(e)}` };
        }
        return updated;
      });
    }
    setLoading(false);
    inputRef.current?.focus();
  }, [input, loading, sessionId, thinkingMode]);

  const sendChat = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    setEntries((prev) => [...prev, { type: "chat-user", content: text }]);
    setInput("");
    setLoading(true);

    // Add empty streaming placeholder
    setEntries((prev) => [...prev, { type: "chat-reply", content: "" }]);

    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          dataset_id: datasetId, student_uid: student.uid,
          message: text, session_id: sessionId,
          thinking_mode: thinkingMode,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let fullReply = "";
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.token) {
              fullReply += data.token;
              setEntries((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { type: "chat-reply", content: fullReply };
                return updated;
              });
            }
            if (data.session_id && !sessionId) setSessionId(data.session_id);
            if (data.error) {
              setEntries((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { type: "system", content: data.error };
                return updated;
              });
            }
          } catch { /* skip malformed SSE lines */ }
        }
      }
    } catch (e) {
      setEntries((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.type === "chat-reply" && !last.content) {
          updated[updated.length - 1] = { type: "system", content: `Error: ${e instanceof Error ? e.message : String(e)}` };
        }
        return updated;
      });
    }
    setLoading(false);
    inputRef.current?.focus();
  }, [input, loading, datasetId, student.uid, sessionId, thinkingMode]);

  const handleSubmit = useCallback(() => {
    if (mode === "review" && currentQuestion && !reviewComplete) {
      if (inputMode === "ask") {
        askReviewQuestion();
      } else {
        submitAnswer();
      }
    } else {
      if (mode === "idle") setMode("chat");
      sendChat();
    }
  }, [mode, currentQuestion, reviewComplete, inputMode, submitAnswer, askReviewQuestion, sendChat]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  const mastery = student.final_mastery ?? [];
  const avgMastery = mastery.length > 0 ? mastery.reduce((a, b) => a + b, 0) / mastery.length : 0;

  if (connected === false) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Learning Fellow Chat
            <Badge variant="outline" className="bg-red-50 text-red-600 border-red-200">Unavailable</Badge>
          </CardTitle>
          <CardDescription>The review service is not responding. Make sure the backend is running.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="bg-muted rounded-lg p-6 space-y-3">
            <p className="text-sm font-medium">To start the backend, run:</p>
            <pre className="bg-background rounded p-3 text-xs font-mono overflow-x-auto">
              {"cd backend\nuv run fastapi dev main.py"}
            </pre>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {/* Score bar */}
      {progress && progress.total > 0 && (
        <ScoreBar progress={progress} thinkingMode={thinkingMode} />
      )}

      {/* Chat card */}
      <Card className="overflow-hidden border-border/60">
        <div className="flex" style={{ height: "calc(100vh - 320px)", minHeight: "480px", maxHeight: "720px" }}>
          {/* ── Main chat column ── */}
          <div className="flex flex-col flex-1 min-w-0">
          {/* Messages area */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {entries.length === 0 && !loading && (
              <WelcomeScreen
                avgMastery={avgMastery}
                reviewOptions={reviewOptions}
              />
            )}

            {mode === "idle" && (
              <SessionSetupPanel
                sessionType={sessionType}
                reviewOptions={reviewOptions}
                selectedSkills={selectedSkills}
                setSelectedSkills={setSelectedSkills}
                customSkill={customSkill}
                setCustomSkill={setCustomSkill}
                questionCount={questionCount}
                setQuestionCount={setQuestionCount}
                thinkingMode={thinkingMode}
                loading={loading}
                onSelectAuto={() => setSessionType("auto")}
                onSelectManual={() => setSessionType("manual")}
                onBack={() => setSessionType(null)}
                onStart={startReview}
                onJustChat={() => { setMode("chat"); inputRef.current?.focus(); }}
              />
            )}

            {entries.map((entry, i) => (
              <EntryBubble key={i} entry={entry} />
            ))}

            {/* Active question card */}
            {currentQuestion && !lastFeedback && !loading && (
              <QuestionCard question={currentQuestion} hints={hints} hintLoading={hintLoading} hintsFinal={hintsFinal} onFetchHint={fetchHint} />
            )}

            {/* Next question preview after feedback */}
            {currentQuestion && lastFeedback && !loading && (
              <QuestionCard question={currentQuestion} hints={[]} hintLoading={false} hintsFinal={false} onFetchHint={() => {}} />
            )}

            {loading && <TypingIndicator />}
            <div ref={scrollRef} />
          </div>

          {/* Quick actions */}
          {mode === "review" && currentQuestion && !loading && (
            <div className="px-5 py-2.5 border-t border-border/60 flex gap-2 overflow-x-auto bg-muted/30">
              {!hintsFinal && (
                <QuickBtn onClick={fetchHint} label={hints.length === 0 ? "Show Hint" : "Next Hint"} disabled={hintLoading} />
              )}
              <QuickBtn onClick={explainConcept} label="Explain" />
              <QuickBtn onClick={skipQuestion} label="Skip" />
              <QuickBtn
                onClick={() => {
                  saveConversationSnapshot("Quit review session");
                  localStorage.removeItem(`arcd_review_${datasetId}_${student.uid}`);
                  resetState();
                  setMode("idle");
                  setReviewComplete(false);
                  setLastFeedback(null);
                  setCurrentQuestion(null);
                }}
                label="Quit Review"
              />
            </div>
          )}

          {reviewComplete && (
            <div className="px-5 py-2.5 border-t border-border/60 flex gap-2 overflow-x-auto bg-muted/30">
              <QuickBtn onClick={() => { resetState(); }} label="Start New Review" />
              <QuickBtn onClick={() => { setMode("chat"); inputRef.current?.focus(); }} label="Ask a Question" />
            </div>
          )}

          {/* Input */}
          <div className="border-t border-border/60 p-4 bg-card">
            <div className="flex items-center justify-between mb-2">
              {mode === "review" && currentQuestion && !reviewComplete ? (
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => setInputMode("answer")}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                      inputMode === "answer"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted/60 text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    Answer
                  </button>
                  <button
                    onClick={() => setInputMode("ask")}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                      inputMode === "ask"
                        ? "bg-blue-500 text-white"
                        : "bg-muted/60 text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    Ask a Question
                  </button>
                </div>
              ) : <div />}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setHistoryPanelOpen((p) => !p)}
                  title="Conversation History"
                  className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                    historyPanelOpen
                      ? "bg-muted border-border/80 text-foreground"
                      : "border-border/60 text-muted-foreground hover:bg-muted/60"
                  }`}
                >
                  📋 History
                </button>
                <ThinkingModeToggle mode={thinkingMode} onChange={setThinkingMode} />
              </div>
            </div>
            <div className="flex gap-3">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  mode === "review" && currentQuestion
                    ? inputMode === "ask"
                      ? "Ask the Learning Fellow anything about this question..."
                      : "Type your answer..."
                    : "Ask the Learning Fellow anything..."
                }
                disabled={loading}
                className={`flex-1 rounded-full border px-4 py-2.5 text-sm focus:outline-none focus:ring-2 disabled:opacity-50 transition-colors ${
                  inputMode === "ask" && mode === "review" && currentQuestion
                    ? "border-blue-500/40 bg-blue-500/5 focus:bg-blue-500/10 focus:ring-blue-500/40"
                    : "border-border/80 bg-muted/40 focus:bg-muted/60 focus:ring-primary/40"
                }`}
              />
              <button
                onClick={handleSubmit}
                disabled={!input.trim() || loading}
                className={`px-6 py-2.5 rounded-full text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors ${
                  inputMode === "ask" && mode === "review" && currentQuestion
                    ? "bg-blue-500 text-white hover:bg-blue-600"
                    : "bg-primary text-primary-foreground hover:bg-primary/90"
                }`}
              >
                {mode === "review" && currentQuestion
                  ? inputMode === "ask" ? "Ask" : "Submit"
                  : "Send"}
              </button>
            </div>
          </div>
          </div>{/* end main chat column */}

          {/* ── History sidebar ── */}
          {historyPanelOpen && (
            <div className="w-72 border-l border-border/60 flex flex-col overflow-hidden shrink-0">
              <div className="flex items-center justify-between px-3 py-2.5 border-b border-border/40 bg-muted/20">
                <span className="text-sm font-medium">Conversation History</span>
                <button
                  onClick={() => setHistoryPanelOpen(false)}
                  className="text-muted-foreground hover:text-foreground text-xl leading-none px-1"
                >
                  ×
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
                {conversationHistory.length === 0 ? (
                  <p className="text-xs text-muted-foreground p-2">No saved conversations yet.</p>
                ) : (
                  conversationHistory.map((h) => (
                    <div key={h.id} className="rounded-lg border border-border/60 px-2.5 py-2 space-y-1">
                      {editingHistoryId === h.id ? (
                        <div className="flex items-center gap-1">
                          <input
                            value={editingLabel}
                            onChange={(e) => setEditingLabel(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") { renameHistorySnapshot(h.id, editingLabel); setEditingHistoryId(null); }
                              if (e.key === "Escape") setEditingHistoryId(null);
                            }}
                            className="flex-1 rounded border border-border/80 bg-muted/40 px-2 py-0.5 text-xs"
                            autoFocus
                          />
                          <button
                            onClick={() => { renameHistorySnapshot(h.id, editingLabel); setEditingHistoryId(null); }}
                            className="px-1.5 py-0.5 text-xs rounded border border-border/80 hover:bg-muted/70"
                          >✓</button>
                        </div>
                      ) : (
                        <p className="text-xs font-medium truncate">{h.label}</p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        {new Date(h.createdAt).toLocaleString()} · {h.entries.length} msgs
                      </p>
                      <div className="flex gap-1 pt-0.5">
                        <button
                          onClick={() => { setEditingHistoryId(h.id); setEditingLabel(h.label); }}
                          className="flex-1 py-1 text-xs rounded border border-border/80 hover:bg-muted/70"
                        >Label</button>
                        <button
                          onClick={() => {
                            setOpenHistoryTabs((prev) => {
                              if (prev.some((tab) => tab.id === h.id)) return prev;
                              return [...prev, { id: h.id, label: h.label, entries: h.entries }];
                            });
                            setActiveHistoryTabId(h.id);
                            setHistoryPanelOpen(false);
                          }}
                          className="flex-1 py-1 text-xs rounded border border-primary/60 text-primary hover:bg-primary/10"
                        >Load</button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

        </div>
      </Card>

      {openHistoryTabs.length > 0 && (
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle className="text-base">Saved Conversation Tabs</CardTitle>
            <CardDescription>
              Open snapshots next to your current chat. Closing a tab does not remove it from history.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {openHistoryTabs.map((tab) => {
                const isActive = tab.id === activeHistoryTabId;
                return (
                  <div
                    key={tab.id}
                    className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
                      isActive ? "border-primary bg-primary/10 text-primary" : "border-border/70"
                    }`}
                  >
                    <button onClick={() => setActiveHistoryTabId(tab.id)} className="text-left">
                      {tab.label}
                    </button>
                    <button
                      onClick={() => closeHistoryTab(tab.id)}
                      className="text-muted-foreground hover:text-foreground"
                      title="Close tab"
                    >
                      ×
                    </button>
                  </div>
                );
              })}
            </div>

            {activeHistoryTabId && (
              <div className="rounded-lg border border-border/60 bg-muted/20 p-3 max-h-80 overflow-y-auto space-y-3">
                {(openHistoryTabs.find((tab) => tab.id === activeHistoryTabId)?.entries ?? []).map((entry, i) => (
                  <EntryBubble key={`${activeHistoryTabId}-${i}`} entry={entry} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Student notebook */}
      <StudentNotebook key={`${datasetId}-${student.uid}`} datasetId={datasetId} studentUid={student.uid} />

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base">Session Analysis Feedback</CardTitle>
          <CardDescription>Constructive guidance based on your latest review session.</CardDescription>
        </CardHeader>
        <CardContent>
          {analysisLoading ? (
            <p className="text-sm text-muted-foreground">Generating analysis...</p>
          ) : sessionAnalysis ? (
            <div className="text-sm leading-relaxed"><MarkdownMath text={sessionAnalysis} /></div>
          ) : (
            <p className="text-sm text-muted-foreground">Complete a review session to receive personalized analysis feedback.</p>
          )}
        </CardContent>
      </Card>

    </div>
  );
}


/* ═══════════════════════════ Session Setup Components ═══════════════════════════ */

interface SessionSetupPanelProps {
  sessionType: "auto" | "manual" | null;
  reviewOptions: {
    suggested_skills: string[];
    selected_skills: string[];
    mastery_map: Record<string, number>;
    question_count_bounds?: { min: number; max: number; default_fast: number; default_deep: number };
  } | null;
  selectedSkills: string[];
  setSelectedSkills: React.Dispatch<React.SetStateAction<string[]>>;
  customSkill: string;
  setCustomSkill: React.Dispatch<React.SetStateAction<string>>;
  questionCount: number;
  setQuestionCount: React.Dispatch<React.SetStateAction<number>>;
  thinkingMode: "fast" | "deep";
  loading: boolean;
  onSelectAuto: () => void;
  onSelectManual: () => void;
  onBack: () => void;
  onStart: () => void;
  onJustChat: () => void;
}

function SessionSetupPanel({
  sessionType, reviewOptions, selectedSkills, setSelectedSkills,
  customSkill, setCustomSkill, questionCount, setQuestionCount,
  thinkingMode, loading, onSelectAuto, onSelectManual, onBack, onStart, onJustChat,
}: SessionSetupPanelProps) {
  if (sessionType === null) {
    return (
      <SessionTypeChooser
        reviewOptions={reviewOptions}
        onSelectAuto={onSelectAuto}
        onSelectManual={onSelectManual}
        onJustChat={onJustChat}
      />
    );
  }
  if (sessionType === "auto") {
    return (
      <AutoSessionSetup
        reviewOptions={reviewOptions}
        questionCount={questionCount}
        setQuestionCount={setQuestionCount}
        thinkingMode={thinkingMode}
        loading={loading}
        onBack={onBack}
        onStart={onStart}
      />
    );
  }
  return (
    <ManualSessionSetup
      reviewOptions={reviewOptions}
      selectedSkills={selectedSkills}
      setSelectedSkills={setSelectedSkills}
      customSkill={customSkill}
      setCustomSkill={setCustomSkill}
      questionCount={questionCount}
      setQuestionCount={setQuestionCount}
      loading={loading}
      onBack={onBack}
      onStart={onStart}
    />
  );
}


function SessionTypeChooser({ reviewOptions, onSelectAuto, onSelectManual, onJustChat }: {
  reviewOptions: {
    suggested_skills: string[];
    selected_skills: string[];
    mastery_map: Record<string, number>;
  } | null;
  onSelectAuto: () => void;
  onSelectManual: () => void;
  onJustChat: () => void;
}) {
  const masteryMap = reviewOptions?.mastery_map ?? {};
  const suggested = reviewOptions?.suggested_skills ?? [];
  const enrolled = reviewOptions?.selected_skills ?? [];

  const masteryColor = (m: number) =>
    m >= 0.65 ? "text-emerald-600 dark:text-emerald-400" :
    m >= 0.40 ? "text-amber-600 dark:text-amber-400" :
    "text-red-600 dark:text-red-400";

  const masteryBg = (m: number) =>
    m >= 0.65 ? "bg-emerald-50 border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-800" :
    m >= 0.40 ? "bg-amber-50 border-amber-200 dark:bg-amber-950/30 dark:border-amber-800" :
    "bg-red-50 border-red-200 dark:bg-red-950/30 dark:border-red-800";

  return (
    <div className="space-y-5 py-2">
      <div className="text-center space-y-1">
        <h3 className="font-semibold text-base">Choose Your Review Mode</h3>
        <p className="text-xs text-muted-foreground">
          Let the model guide you or build your own session from scratch.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Automatic */}
        <button
          onClick={onSelectAuto}
          className="group text-left rounded-xl border-2 border-blue-200 dark:border-blue-800 bg-blue-50/60 dark:bg-blue-950/20 p-4 hover:border-blue-400 dark:hover:border-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/40 transition-all"
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">🤖</span>
            <div>
              <p className="font-semibold text-sm text-blue-700 dark:text-blue-300">Automatic Review</p>
              <p className="text-[11px] text-blue-600/70 dark:text-blue-400/70">Model-guided · optimised for you</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
            The AI analyses your mastery profile and selects the most impactful skills to review right now.
          </p>
          {suggested.length > 0 ? (
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">Recommended skills</p>
              <div className="flex flex-wrap gap-1.5">
                {suggested.slice(0, 5).map((s) => {
                  const m = masteryMap[s] ?? 0;
                  return (
                    <span key={s} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${masteryBg(m)}`}>
                      <span>{s}</span>
                      <span className={`font-semibold ${masteryColor(m)}`}>{(m * 100).toFixed(0)}%</span>
                    </span>
                  );
                })}
                {suggested.length > 5 && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] border border-border/50 text-muted-foreground">
                    +{suggested.length - 5} more
                  </span>
                )}
              </div>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground italic">Loading recommendations…</p>
          )}
          <div className="mt-4 w-full rounded-lg bg-blue-500 text-white text-xs font-semibold py-2 text-center group-hover:bg-blue-600 transition-colors">
            Start Automatic Session →
          </div>
        </button>

        {/* Manual */}
        <button
          onClick={onSelectManual}
          className="group text-left rounded-xl border-2 border-violet-200 dark:border-violet-800 bg-violet-50/60 dark:bg-violet-950/20 p-4 hover:border-violet-400 dark:hover:border-violet-600 hover:bg-violet-50 dark:hover:bg-violet-950/40 transition-all"
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">📝</span>
            <div>
              <p className="font-semibold text-sm text-violet-700 dark:text-violet-300">Manual Review</p>
              <p className="text-[11px] text-violet-600/70 dark:text-violet-400/70">Student-directed · your choice</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
            Pick exactly which skills to review. Great when you want to focus on a specific topic or chapter.
          </p>
          {enrolled.length > 0 ? (
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">
                {enrolled.length} skill{enrolled.length !== 1 ? "s" : ""} available to choose from
              </p>
              <div className="flex flex-wrap gap-1.5">
                {enrolled.slice(0, 5).map((s) => (
                  <span key={s} className="px-2 py-0.5 rounded-full text-[11px] border border-violet-200 dark:border-violet-700 text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-950/20">
                    {s}
                  </span>
                ))}
                {enrolled.length > 5 && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] border border-border/50 text-muted-foreground">
                    +{enrolled.length - 5} more
                  </span>
                )}
              </div>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground italic">Loading skills…</p>
          )}
          <div className="mt-4 w-full rounded-lg bg-violet-500 text-white text-xs font-semibold py-2 text-center group-hover:bg-violet-600 transition-colors">
            Build My Session →
          </div>
        </button>
      </div>

      <div className="text-center">
        <button onClick={onJustChat} className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors">
          Just ask the Learning Fellow a question instead
        </button>
      </div>
    </div>
  );
}


function AutoSessionSetup({ reviewOptions, questionCount, setQuestionCount, thinkingMode, loading, onBack, onStart }: {
  reviewOptions: {
    suggested_skills: string[];
    selected_skills: string[];
    mastery_map: Record<string, number>;
    question_count_bounds?: { min: number; max: number; default_fast: number; default_deep: number };
  } | null;
  questionCount: number;
  setQuestionCount: React.Dispatch<React.SetStateAction<number>>;
  thinkingMode: "fast" | "deep";
  loading: boolean;
  onBack: () => void;
  onStart: () => void;
}) {
  const suggested = reviewOptions?.suggested_skills ?? [];
  const masteryMap = reviewOptions?.mastery_map ?? {};
  const bounds = reviewOptions?.question_count_bounds;

  const masteryBand = (m: number) =>
    m >= 0.65 ? { label: "Strong", color: "text-emerald-600 dark:text-emerald-400", bar: "bg-emerald-500" } :
    m >= 0.40 ? { label: "Developing", color: "text-amber-600 dark:text-amber-400", bar: "bg-amber-500" } :
    { label: "Needs work", color: "text-red-600 dark:text-red-400", bar: "bg-red-500" };

  return (
    <Card className="border-blue-200 dark:border-blue-800">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-muted-foreground hover:text-foreground text-xs flex items-center gap-1">
            ← Back
          </button>
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <span>🤖</span> Automatic Review Session
            </CardTitle>
            <CardDescription>Skills selected by the AI based on your current mastery profile</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Skills the model has selected */}
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {suggested.length} skill{suggested.length !== 1 ? "s" : ""} the model recommends right now
          </p>
          {suggested.length > 0 ? (
            <div className="space-y-2">
              {suggested.map((s) => {
                const m = masteryMap[s] ?? 0;
                const band = masteryBand(m);
                return (
                  <div key={s} className="flex items-center gap-3 p-2.5 rounded-lg border border-border/50 bg-muted/20">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-sm font-medium truncate">{s}</span>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          <span className={`text-[11px] font-semibold ${band.color}`}>{band.label}</span>
                          <span className="text-xs font-bold text-muted-foreground">{(m * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${band.bar}`} style={{ width: `${m * 100}%` }} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border/50 p-6 text-center">
              <p className="text-sm text-muted-foreground">Loading model recommendations…</p>
            </div>
          )}
        </div>

        {/* Question count */}
        <div className="flex items-center gap-3 pt-1">
          <label className="text-sm text-muted-foreground whitespace-nowrap">Questions per session:</label>
          <input
            type="number"
            min={bounds?.min ?? 1}
            max={bounds?.max ?? 20}
            value={questionCount}
            onChange={(e) => setQuestionCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            className="w-20 rounded-md border border-border/80 bg-muted/40 px-2 py-1 text-sm"
          />
          <span className="text-xs text-muted-foreground">
            {thinkingMode === "deep" ? "Deep review mode" : "Fast review mode"}
          </span>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-border/40">
          <p className="text-xs text-muted-foreground">
            {suggested.length} skill{suggested.length !== 1 ? "s" : ""} · {questionCount} question{questionCount !== 1 ? "s" : ""}
          </p>
          <button
            onClick={onStart}
            disabled={loading || suggested.length === 0}
            className="px-5 py-2 rounded-lg bg-blue-500 text-white text-sm font-semibold hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Starting…" : "Start Automatic Review"}
          </button>
        </div>
      </CardContent>
    </Card>
  );
}


function ManualSessionSetup({ reviewOptions, selectedSkills, setSelectedSkills, customSkill, setCustomSkill,
  questionCount, setQuestionCount, loading, onBack, onStart }: {
  reviewOptions: {
    suggested_skills: string[];
    selected_skills: string[];
    mastery_map: Record<string, number>;
    question_count_bounds?: { min: number; max: number; default_fast: number; default_deep: number };
  } | null;
  selectedSkills: string[];
  setSelectedSkills: React.Dispatch<React.SetStateAction<string[]>>;
  customSkill: string;
  setCustomSkill: React.Dispatch<React.SetStateAction<string>>;
  questionCount: number;
  setQuestionCount: React.Dispatch<React.SetStateAction<number>>;
  loading: boolean;
  onBack: () => void;
  onStart: () => void;
}) {
  const suggested = reviewOptions?.suggested_skills ?? [];
  const enrolled = reviewOptions?.selected_skills ?? [];
  const masteryMap = reviewOptions?.mastery_map ?? {};
  const bounds = reviewOptions?.question_count_bounds;

  const toggle = (s: string) =>
    setSelectedSkills((prev) => prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]);

  const masteryColor = (m: number) =>
    m >= 0.65 ? "text-emerald-600 dark:text-emerald-400" :
    m >= 0.40 ? "text-amber-600 dark:text-amber-400" :
    "text-red-500 dark:text-red-400";

  return (
    <Card className="border-violet-200 dark:border-violet-800">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-muted-foreground hover:text-foreground text-xs flex items-center gap-1">
            ← Back
          </button>
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <span>📝</span> Build Your Session
            </CardTitle>
            <CardDescription>Pick the skills you want to focus on in this session</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Recommended by model */}
        {suggested.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              🎯 Model-recommended (tap to toggle)
            </p>
            <div className="flex flex-wrap gap-2">
              {suggested.map((s) => {
                const m = masteryMap[s] ?? 0;
                const isSelected = selectedSkills.includes(s);
                return (
                  <button
                    key={s}
                    onClick={() => toggle(s)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                      isSelected
                        ? "bg-violet-500 text-white border-violet-500"
                        : "border-violet-300 dark:border-violet-700 text-violet-700 dark:text-violet-300 hover:bg-violet-50 dark:hover:bg-violet-950/30"
                    }`}
                  >
                    <span>{s}</span>
                    <span className={isSelected ? "text-violet-200" : masteryColor(m)}>
                      {(m * 100).toFixed(0)}%
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* All enrolled skills */}
        {enrolled.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">All skills</p>
            <div className="max-h-44 overflow-y-auto rounded-lg border border-border/50 bg-muted/10 p-2 grid grid-cols-1 sm:grid-cols-2 gap-1">
              {enrolled.map((s) => {
                const m = masteryMap[s] ?? 0;
                return (
                  <label key={s} className="flex items-center gap-2 text-sm px-2 py-1.5 rounded-md hover:bg-muted/50 cursor-pointer transition-colors">
                    <input
                      type="checkbox"
                      checked={selectedSkills.includes(s)}
                      onChange={() => toggle(s)}
                      className="accent-violet-500"
                    />
                    <span className="flex-1 truncate">{s}</span>
                    <span className={`text-[11px] font-semibold flex-shrink-0 ${masteryColor(m)}`}>
                      {(m * 100).toFixed(0)}%
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {/* Custom skill */}
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">Add a skill not in the list:</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={customSkill}
              onChange={(e) => setCustomSkill(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const s = customSkill.trim();
                  if (!s) return;
                  setSelectedSkills((prev) => prev.includes(s) ? prev : [...prev, s]);
                  setCustomSkill("");
                }
              }}
              placeholder="Type skill name and press Enter..."
              className="flex-1 rounded-md border border-border/80 bg-muted/40 px-3 py-1.5 text-sm"
            />
            <button
              onClick={() => {
                const s = customSkill.trim();
                if (!s) return;
                setSelectedSkills((prev) => prev.includes(s) ? prev : [...prev, s]);
                setCustomSkill("");
              }}
              className="px-3 py-1.5 rounded-md bg-muted border border-border/80 text-sm hover:bg-muted/70"
            >
              Add
            </button>
          </div>
        </div>

        {/* Selected summary + question count */}
        {selectedSkills.length > 0 && (
          <div className="space-y-2 rounded-lg border border-border/50 bg-muted/20 p-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Selected ({selectedSkills.length})
            </p>
            <div className="flex flex-wrap gap-1.5">
              {selectedSkills.map((s) => (
                <span
                  key={s}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-700"
                >
                  {s}
                  <button
                    onClick={() => setSelectedSkills((prev) => prev.filter((x) => x !== s))}
                    className="ml-0.5 text-violet-400 hover:text-violet-700 dark:hover:text-violet-200"
                  >×</button>
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          <label className="text-sm text-muted-foreground whitespace-nowrap">Questions:</label>
          <input
            type="number"
            min={bounds?.min ?? 1}
            max={bounds?.max ?? 20}
            value={questionCount}
            onChange={(e) => setQuestionCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            className="w-20 rounded-md border border-border/80 bg-muted/40 px-2 py-1 text-sm"
          />
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-border/40">
          <p className="text-xs text-muted-foreground">
            {selectedSkills.length} skill{selectedSkills.length !== 1 ? "s" : ""} selected · {questionCount} question{questionCount !== 1 ? "s" : ""}
          </p>
          <button
            onClick={onStart}
            disabled={loading || selectedSkills.length === 0}
            className="px-5 py-2 rounded-lg bg-violet-500 text-white text-sm font-semibold hover:bg-violet-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Starting…" : "Start Manual Review"}
          </button>
        </div>
      </CardContent>
    </Card>
  );
}


/* ═══════════════════════════ Sub-components ═══════════════════════════ */

function ScoreBar({ progress, thinkingMode }: { progress: Progress; thinkingMode: "fast" | "deep" }) {
  const pct = progress.max_score > 0 ? (progress.score / progress.max_score) * 100 : 0;
  const fillColor = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-blue-500";

  return (
    <Card className="border-border/60">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">Review Progress</span>
            <Badge variant="outline" className="text-xs border-border/60">
              Question {Math.min(progress.current, progress.total)} of {progress.total}
            </Badge>
            <Badge
              variant="outline"
              className={`text-xs ${
                thinkingMode === "deep"
                  ? "border-purple-500/40 text-purple-300"
                  : "border-amber-500/40 text-amber-300"
              }`}
            >
              {thinkingMode === "deep" ? "Deep Review" : "Fast Review"}
            </Badge>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-green-400 font-semibold">{progress.correct} correct</span>
            <span className="text-muted-foreground">
              Score: {progress.score}/{progress.max_score}
            </span>
          </div>
        </div>
        <div className="w-full bg-muted/60 rounded-full h-2.5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ease-out ${fillColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        {progress.total > 0 && (
          <div className="flex justify-between mt-2 px-1">
            {Array.from({ length: progress.total }, (_, i) => (
              <div key={i} className="flex flex-col items-center">
                <div className={`w-2.5 h-2.5 rounded-full border-2 transition-colors ${
                  i < progress.current - 1
                    ? (i < progress.correct ? "bg-green-500 border-green-500" : "bg-red-400 border-red-400")
                    : i === progress.current - 1
                    ? "bg-primary border-primary animate-pulse"
                    : "bg-muted border-muted-foreground/20"
                }`} />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}


function WelcomeScreen({ avgMastery, reviewOptions }: {
  avgMastery: number;
  reviewOptions: {
    suggested_skills: string[];
    selected_skills: string[];
    mastery_map: Record<string, number>;
  } | null;
}) {
  const masteryMap = reviewOptions?.mastery_map ?? {};
  const entries = Object.entries(masteryMap);

  const strengths = entries
    .filter(([, v]) => v >= 0.65)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([k]) => k);

  const weaknesses = entries
    .filter(([, v]) => v < 0.65)
    .sort((a, b) => a[1] - b[1])
    .slice(0, 3)
    .map(([k]) => k);

  return (
    <div className="flex flex-col items-center justify-center py-6 text-center space-y-5">
      <div className="w-14 h-14 rounded-full bg-primary/15 flex items-center justify-center">
        <span className="text-3xl">🎓</span>
      </div>
      <div className="space-y-1.5 max-w-sm">
        <h3 className="font-semibold text-lg">Welcome to Learning Fellow</h3>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Your AI-powered review companion. Select skills and questions below, then start a session.
        </p>
      </div>

      {/* Mastery snapshot */}
      <div className="w-full max-w-sm rounded-xl border border-border/60 bg-muted/30 p-4 text-left space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Mastery Snapshot</span>
          <span className="text-sm font-bold text-primary">{(avgMastery * 100).toFixed(1)}% avg</span>
        </div>
        {strengths.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-green-600 dark:text-green-400">✓ Strengths</p>
            <div className="flex flex-wrap gap-1.5">
              {strengths.map((s) => (
                <span key={s} className="px-2 py-0.5 rounded-full text-xs bg-green-50 text-green-700 border border-green-200 dark:bg-green-950/40 dark:text-green-300 dark:border-green-800">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
        {weaknesses.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-amber-600 dark:text-amber-400">⚠ Focus areas</p>
            <div className="flex flex-wrap gap-1.5">
              {weaknesses.map((s) => (
                <span key={s} className="px-2 py-0.5 rounded-full text-xs bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
        {entries.length === 0 && (
          <p className="text-xs text-muted-foreground">No mastery data yet — complete a session to see your profile.</p>
        )}
      </div>
    </div>
  );
}


function QuestionCard({ question, hints, hintLoading, hintsFinal, onFetchHint }: {
  question: QuestionData;
  hints: string[];
  hintLoading: boolean;
  hintsFinal: boolean;
  onFetchHint: () => void;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-full bg-blue-500/15 flex items-center justify-center flex-shrink-0 mt-0.5">
        <span className="text-sm">📝</span>
      </div>
      <div className="flex-1 max-w-[85%]">
        <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
          <Badge variant="outline" className="text-[10px] border-blue-400/40 text-blue-400">
            {question.index}/{question.total}
          </Badge>
          <span className="text-xs font-medium text-blue-400">{question.skill_name}</span>
          {question.is_pco && (
            <Badge variant="destructive" className="text-[10px]">PCO</Badge>
          )}
          <Badge variant="outline" className="text-[10px] border-muted-foreground/30 text-muted-foreground">
            {question.difficulty}
          </Badge>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-2xl rounded-tl-sm px-4 py-3 space-y-3">
          <p className="text-sm leading-relaxed"><MathText text={question.question ?? ""} /></p>
        </div>
        {/* Progressive hints */}
        {hints.length > 0 && (
          <div className="mt-2 space-y-2">
            {hints.map((hint, i) => (
              <div key={i} className="bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2 text-xs text-amber-300">
                <strong>Hint {i + 1}:</strong> <MathText text={hint} />
              </div>
            ))}
          </div>
        )}
        {hintLoading && (
          <div className="mt-2 bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2 text-xs text-amber-300/60 animate-pulse">
            Generating next hint...
          </div>
        )}
        {hints.length === 0 && !hintLoading && question.hint && !hintsFinal && (
          <button onClick={onFetchHint}
            className="mt-1.5 text-xs text-blue-400 hover:text-blue-300 hover:underline">
            Need a hint?
          </button>
        )}
      </div>
    </div>
  );
}


function EntryBubble({ entry }: { entry: ChatEntry }) {
  if (entry.type === "system") {
    return (
      <div className="flex justify-center">
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg px-4 py-2 text-xs text-yellow-300 max-w-lg">
          {entry.content}
        </div>
      </div>
    );
  }

  if (entry.type === "greeting" || entry.type === "chat-reply") {
    return (
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-primary/15 flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-sm">🎓</span>
        </div>
        <div className="max-w-[80%] bg-muted/80 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed">
          <MarkdownMath text={entry.content} />
        </div>
      </div>
    );
  }

  if (entry.type === "answer" || entry.type === "chat-user") {
    return (
      <div className="flex items-start gap-3 flex-row-reverse">
        <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-sm">👤</span>
        </div>
        <div className="max-w-[75%] bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-3 text-sm">
          {entry.content}
        </div>
      </div>
    );
  }

  if (entry.type === "feedback") {
    const fb = entry.data as FeedbackData | null;
    const isCorrect = fb?.correct ?? false;
    const delta = fb?.suggested_mastery_delta;
    return (
      <div className="flex items-start gap-3">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
          isCorrect ? "bg-green-500/15" : "bg-red-500/15"
        }`}>
          <span className="text-sm">{isCorrect ? "✅" : "❌"}</span>
        </div>
        <div className={`max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3 text-sm space-y-2 ${
          isCorrect
            ? "bg-green-500/10 border border-green-500/20"
            : "bg-red-500/10 border border-red-500/20"
        }`}>
          <div className="flex items-center justify-between gap-2">
            <p className={`font-medium ${isCorrect ? "text-green-400" : "text-red-400"}`}>
              {isCorrect ? "Correct!" : "Not quite right"}
            </p>
            {delta != null && delta !== 0 && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                delta > 0
                  ? "bg-green-500/20 text-green-400"
                  : "bg-red-500/20 text-red-400"
              }`}>
                Mastery {delta > 0 ? "+" : ""}{(delta * 100).toFixed(2)}%
              </span>
            )}
          </div>
          <div className="text-sm"><MarkdownMath text={fb?.message ?? ""} /></div>
          {!isCorrect && fb?.correct_answer && (
            <div className="bg-background/40 rounded-lg px-3 py-2 text-xs">
              <strong>Answer:</strong> <MathText text={fb.correct_answer ?? ""} />
            </div>
          )}
          {fb?.explanation && (
            <div className="text-xs text-muted-foreground"><MarkdownMath text={fb.explanation} /></div>
          )}
        </div>
      </div>
    );
  }

  if (entry.type === "complete") {
    return (
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-primary/15 flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-sm">🏆</span>
        </div>
        <div className="max-w-[80%] bg-gradient-to-r from-primary/5 to-primary/10 border border-primary/20 rounded-2xl rounded-tl-sm px-4 py-3 text-sm">
          <MarkdownMath text={entry.content} />
        </div>
      </div>
    );
  }

  if (entry.type === "summary" && entry.data && "skills_summary" in entry.data) {
    return <ReviewSummaryCard summary={entry.data as ReviewSummaryData} />;
  }

  return null;
}



function ReviewSummaryCard({ summary }: { summary: ReviewSummaryData }) {
  const [showDetails, setShowDetails] = useState(false);
  const grade =
    summary.percentage >= 90 ? "A" :
    summary.percentage >= 80 ? "B" :
    summary.percentage >= 70 ? "C" :
    summary.percentage >= 60 ? "D" : "F";
  const gradeColor =
    grade === "A" ? "text-green-400" :
    grade === "B" ? "text-blue-400" :
    grade === "C" ? "text-yellow-400" :
    grade === "D" ? "text-orange-400" : "text-red-400";
  const gradeBg =
    grade === "A" ? "bg-green-500/15 border-green-500/30" :
    grade === "B" ? "bg-blue-500/15 border-blue-500/30" :
    grade === "C" ? "bg-yellow-500/15 border-yellow-500/30" :
    grade === "D" ? "bg-orange-500/15 border-orange-500/30" :
    "bg-red-500/15 border-red-500/30";

  return (
    <div className="w-full space-y-3">
      {/* Score Card */}
      <div className={`rounded-xl border ${gradeBg} p-4`}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm">Review Summary</h3>
          <div className="flex items-center gap-2">
            <span className={`text-2xl font-bold ${gradeColor}`}>{grade}</span>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="bg-background/30 rounded-lg p-2">
            <p className="text-lg font-bold">{summary.score}/{summary.max_score}</p>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Points</p>
          </div>
          <div className="bg-background/30 rounded-lg p-2">
            <p className="text-lg font-bold">{summary.correct_count}/{summary.total_questions}</p>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Correct</p>
          </div>
          <div className="bg-background/30 rounded-lg p-2">
            <p className="text-lg font-bold">{summary.percentage.toFixed(2)}%</p>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Score</p>
          </div>
        </div>
      </div>

      {/* Per-Skill Breakdown */}
      {summary.skills_summary.length > 0 && (
        <div className="rounded-xl border border-border/50 bg-card/50 p-4">
          <h4 className="font-semibold text-xs uppercase tracking-wide text-muted-foreground mb-2">Skill Breakdown</h4>
          <div className="space-y-2">
            {summary.skills_summary.map((sk, i) => {
              const pct = sk.total > 0 ? (sk.correct / sk.total) * 100 : 0;
              const masteryDelta = sk.mastery_end - sk.mastery_start;
              // Urgency: U = (1 - m_end) * (1 - pct/100)  — proxy for decay_s using error rate
              const urgency = (1 - sk.mastery_end) * (sk.total > 0 ? 1 - pct / 100 : 0.5);
              return (
                <div key={i} className="flex items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-medium truncate">{sk.skill_name}</span>
                      {sk.is_pco && <Badge variant="outline" className="text-[9px] px-1 py-0 h-4 border-orange-500/50 text-orange-400">PCO</Badge>}
                      {urgency > 0.3 && (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 h-4 border-red-500/50 text-red-400">
                          U={urgency.toFixed(2)}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-muted-foreground w-14 text-right">{sk.correct}/{sk.total}</span>
                    </div>
                  </div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                    masteryDelta > 0 ? "bg-green-500/20 text-green-400" :
                    masteryDelta < 0 ? "bg-red-500/20 text-red-400" :
                    "bg-muted text-muted-foreground"
                  }`}>
                    {masteryDelta > 0 ? "+" : ""}{(masteryDelta * 100).toFixed(2)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Urgency legend note */}
      {summary.skills_summary.some((sk) => (1 - sk.mastery_end) * (sk.total > 0 ? 1 - (sk.correct / sk.total) : 0.5) > 0.3) && (
        <p className="text-[10px] text-muted-foreground px-1">
          <span className="font-semibold text-red-400">U</span> = urgency score from formula{" "}
          <span className="font-mono">(1 − mastery) × error_rate</span>. High urgency skills need immediate review.
        </p>
      )}

      {/* Strengths & Improvements */}
      <div className="grid grid-cols-2 gap-2">
        {summary.strengths.length > 0 && (
          <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-3">
            <h4 className="text-[10px] uppercase tracking-wide text-green-400 font-semibold mb-1.5">Strengths</h4>
            <ul className="space-y-1">
              {summary.strengths.map((s, i) => (
                <li key={i} className="text-xs flex items-start gap-1">
                  <span className="text-green-400 mt-0.5 flex-shrink-0">&#10003;</span>
                  <span className="text-green-300/80">{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {summary.areas_for_improvement.length > 0 && (
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3">
            <h4 className="text-[10px] uppercase tracking-wide text-amber-400 font-semibold mb-1.5">Focus Areas</h4>
            <ul className="space-y-1">
              {summary.areas_for_improvement.map((s, i) => (
                <li key={i} className="text-xs flex items-start gap-1">
                  <span className="text-amber-400 mt-0.5 flex-shrink-0">&#9679;</span>
                  <span className="text-amber-300/80">{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Per-Question Details (collapsible) */}
      {summary.results.length > 0 && (
        <div className="rounded-xl border border-border/50 bg-card/50 overflow-hidden">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-muted-foreground hover:bg-muted/30 transition-colors"
          >
            <span>Question-by-Question Breakdown</span>
            <span className={`transition-transform ${showDetails ? "rotate-180" : ""}`}>&#9660;</span>
          </button>
          {showDetails && (
            <div className="border-t border-border/50 divide-y divide-border/30">
              {summary.results.map((r, i) => (
                <div key={i} className={`px-4 py-2.5 ${r.is_correct ? "bg-green-500/[0.03]" : "bg-red-500/[0.03]"}`}>
                  <div className="flex items-start gap-2">
                    <span className={`text-xs mt-0.5 flex-shrink-0 ${r.is_correct ? "text-green-400" : "text-red-400"}`}>
                      {r.is_correct ? "&#10003;" : "&#10007;"}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span className="text-xs font-medium">{r.skill_name}</span>
                        <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">{r.difficulty}</Badge>
                        <span className="text-[10px] text-muted-foreground ml-auto">+{r.points} pts</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground mb-1 line-clamp-2">{r.question}</p>
                      {!r.is_correct && (
                        <div className="text-[10px] space-y-0.5">
                          <p><span className="text-red-400/80">Your answer:</span> <span className="text-muted-foreground">{r.student_answer}</span></p>
                          <p><span className="text-green-400/80">Correct:</span> <span className="text-muted-foreground">{r.correct_answer}</span></p>
                        </div>
                      )}
                      {r.feedback_snippet && (
                        <p className="text-[10px] text-muted-foreground/70 mt-1 italic">{r.feedback_snippet}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* LLM Personalized Advice */}
      {summary.llm_feedback && (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm">🎓</span>
            <h4 className="font-semibold text-xs uppercase tracking-wide text-primary/80">Your Study Fellow&apos;s Advice</h4>
          </div>
          <div className="text-xs leading-relaxed prose prose-invert prose-xs max-w-none">
            <MarkdownMath text={summary.llm_feedback} />
          </div>
        </div>
      )}
    </div>
  );
}


function TypingIndicator() {
  return (
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
        <span className="text-sm">🎓</span>
      </div>
      <div className="bg-muted rounded-2xl rounded-tl-sm px-4 py-3">
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
          <span className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
          <span className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
      </div>
    </div>
  );
}


function ThinkingModeToggle({ mode, onChange }: { mode: "fast" | "deep"; onChange: (m: "fast" | "deep") => void }) {
  return (
    <div className="flex items-center gap-1 bg-muted/50 rounded-full p-0.5">
      <button
        onClick={() => onChange("fast")}
        className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all ${
          mode === "fast"
            ? "bg-amber-500/90 text-white shadow-sm"
            : "text-muted-foreground hover:text-foreground"
        }`}
        title="Fast mode: concise, direct responses"
      >
        Fast
      </button>
      <button
        onClick={() => onChange("deep")}
        className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all ${
          mode === "deep"
            ? "bg-purple-500/90 text-white shadow-sm"
            : "text-muted-foreground hover:text-foreground"
        }`}
        title="Deep mode: thorough step-by-step analysis"
      >
        Deep
      </button>
    </div>
  );
}


function QuickBtn({ onClick, label, disabled }: { onClick: () => void; label: string; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`px-3.5 py-1.5 rounded-full border border-border/80 text-xs text-muted-foreground hover:bg-muted/80 hover:text-foreground hover:border-border transition-colors whitespace-nowrap flex-shrink-0 ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}>
      {label}
    </button>
  );
}


/* ═══════════════════════════ Student Notebook ═══════════════════════════ */

interface StudentNote {
  id: string;
  content: string;
  createdAt: number;
}

function StudentNotebook({ datasetId, studentUid }: { datasetId: string; studentUid: string }) {
  const storageKey = `arcd_notes_${datasetId}_${studentUid}`;
  const [notes, setNotes] = useState<StudentNote[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState("");
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (notes.length > 0) {
      try { localStorage.setItem(storageKey, JSON.stringify(notes)); } catch { /* quota */ }
    }
  }, [notes, storageKey]);

  const addNote = () => {
    const text = input.trim();
    if (!text) return;
    setNotes((prev) => [
      { id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, content: text, createdAt: Date.now() },
      ...prev,
    ]);
    setInput("");
  };

  const deleteNote = (id: string) => {
    setNotes((prev) => {
      const updated = prev.filter((n) => n.id !== id);
      if (updated.length === 0) localStorage.removeItem(storageKey);
      return updated;
    });
  };

  return (
    <Card className="border-border/60">
      <CardHeader
        className="cursor-pointer select-none py-3 px-5"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <span className="text-base">📓</span>
            My Notes
            {notes.length > 0 && (
              <Badge variant="secondary" className="text-[10px]">{notes.length}</Badge>
            )}
          </CardTitle>
          <span className={`text-xs text-muted-foreground transition-transform ${isOpen ? "rotate-180" : ""}`}>
            ▼
          </span>
        </div>
        {!isOpen && notes.length === 0 && (
          <CardDescription className="text-xs mt-0.5">
            Jot down key takeaways while you study — they&apos;ll be here when you come back.
          </CardDescription>
        )}
      </CardHeader>
      {isOpen && (
        <CardContent className="pt-0 pb-4 px-5 space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addNote(); } }}
              placeholder="Write a note..."
              className="flex-1 rounded-lg border border-border/80 bg-muted/40 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:bg-muted/60"
            />
            <button
              onClick={addNote}
              disabled={!input.trim()}
              className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-40 transition-colors"
            >
              Save
            </button>
          </div>

          {notes.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-3">
              No notes yet. Write something to remember what you learned!
            </p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {notes.map((note) => (
                <div
                  key={note.id}
                  className="group flex items-start gap-2 bg-muted/40 rounded-lg px-3 py-2"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm leading-relaxed">{note.content}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {new Date(note.createdAt).toLocaleDateString(undefined, {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </p>
                  </div>
                  <button
                    onClick={() => deleteNote(note.id)}
                    className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-400 text-xs transition-opacity flex-shrink-0 mt-0.5"
                    title="Delete note"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
