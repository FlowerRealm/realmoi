"use client";

import React, { useEffect, useState } from "react";
import { Portal } from "./Portal";
import { Cockpit } from "./Cockpit";
import type { AppView, AssistantSession, JobRun, Message, PromptData } from "./types";

const HISTORY_KEY = "realmoi_assistant_history";

function safeJsonParse<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

function sessionTitle(prompt: PromptData): string {
  const s = prompt.problemDescription.trim();
  return (s.slice(0, 18) || "新会话") + (s.length > 18 ? "…" : "");
}

export function AssistantApp({ initialJobId = null }: { initialJobId?: string | null }) {
  const [view, setView] = useState<AppView>(initialJobId ? "cockpit" : "portal");
  const [messages, setMessages] = useState<Message[]>([]);
  const [runs, setRuns] = useState<JobRun[]>(
    initialJobId
      ? [
          {
            jobId: initialJobId,
            createdAt: Date.now(),
          },
        ]
      : []
  );
  const [currentPrompt, setCurrentPrompt] = useState<PromptData | null>(null);

  const [history, setHistory] = useState<AssistantSession[]>([]);
  const [historyHydrated, setHistoryHydrated] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (raw) {
      const parsed = safeJsonParse<AssistantSession[]>(raw);
      if (parsed) setHistory(parsed);
    }
    setHistoryHydrated(true);
  }, []);

  useEffect(() => {
    if (!historyHydrated) return;
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  }, [history, historyHydrated]);

  useEffect(() => {
    if (!initialJobId) return;
    setView("cockpit");
    setRuns((prev) => {
      if (prev.some((r) => r.jobId === initialJobId)) return prev;
      return [{ jobId: initialJobId, createdAt: Date.now() }, ...prev];
    });
  }, [initialJobId]);

  useEffect(() => {
    if (!historyHydrated || !initialJobId || sessionId) return;
    const matched = history.find((session) =>
      (session.runs ?? []).some((run) => run.jobId === initialJobId)
    );
    if (!matched) return;
    setSessionId(matched.id);
    setCurrentPrompt(matched.prompt);
    setMessages(matched.messages ?? []);
    setRuns(
      matched.runs && matched.runs.length > 0
        ? matched.runs
        : [
            {
              jobId: initialJobId,
              createdAt: Date.now(),
            },
          ]
    );
    setView("cockpit");
  }, [history, historyHydrated, initialJobId, sessionId]);

  const persistSession = (opts?: { touchTimestamp?: boolean }) => {
    if (!sessionId || !currentPrompt) return;
    const now = Date.now();
    const session: AssistantSession = {
      id: sessionId,
      title: sessionTitle(currentPrompt),
      timestamp: opts?.touchTimestamp ? now : now,
      prompt: currentPrompt,
      messages,
      runs,
    };

    setHistory((prev) => {
      const idx = prev.findIndex((s) => s.id === sessionId);
      if (idx >= 0) {
        const copy = [...prev];
        copy[idx] = session;
        // Keep most recent on top
        copy.sort((a, b) => b.timestamp - a.timestamp);
        return copy.slice(0, 10);
      }
      return [session, ...prev].slice(0, 10);
    });
  };

  useEffect(() => {
    if (view !== "cockpit") return;
    persistSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, runs, currentPrompt, sessionId, view]);

  const handleStartSession = (data: PromptData) => {
    const id = Date.now().toString();
    setSessionId(id);
    setCurrentPrompt(data);
    setMessages([]);
    setRuns([]);
    setView("cockpit");

    // Write initial history entry.
    setHistory((prev) =>
      [
        {
          id,
          title: sessionTitle(data),
          timestamp: Date.now(),
          prompt: data,
          messages: [],
          runs: [],
        },
        ...prev,
      ].slice(0, 10)
    );
  };

  const handleResumeSession = (session: AssistantSession) => {
    setSessionId(session.id);
    setCurrentPrompt(session.prompt);
    setMessages(session.messages ?? []);
    setRuns(session.runs ?? []);
    setView("cockpit");
  };

  const handleBackToPortal = () => {
    persistSession({ touchTimestamp: true });
    setView("portal");
  };

  return (
    <div className="newapi-scope relative w-screen h-[100dvh] box-border pt-16 md:pt-20 overflow-hidden">

      {view === "portal" ? (
        <Portal onStart={handleStartSession} history={history} onResume={handleResumeSession} />
      ) : (
        <Cockpit
          initialPrompt={currentPrompt}
          initialJobId={initialJobId}
          messages={messages}
          setMessages={setMessages}
          runs={runs}
          setRuns={setRuns}
          onBack={handleBackToPortal}
        />
      )}
    </div>
  );
}
