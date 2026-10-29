"use client";

import { useState } from "react";
import { DotLottieReact } from "@lottiefiles/dotlottie-react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, BookOpen, CalendarDays, FileText, Menu, PanelLeftClose, Plus, ShieldCheck, Sparkles } from "lucide-react";

type Message = { id: string; role: "user" | "assistant"; content: string };
type StreamResult = { response: string; sessionId: string };

const SESSION_STORAGE_KEY = "academic-helpdesk-session-id";

const suggestions = [
  { icon: BookOpen, title: "Academic regulations", text: "What are the attendance requirements?", color: "violet" },
  { icon: CalendarDays, title: "Course information", text: "How do I find my course slot?", color: "blue" },
  { icon: FileText, title: "Email assistant", text: "Draft a sick-leave email to my professor.", color: "pink" },
];

async function streamAssistantResponse(
  question: string,
  sessionId: string,
  onText: (text: string) => void,
  onStatus: (message: string) => void,
): Promise<StreamResult> {
  const chatUrl = process.env.NEXT_PUBLIC_CHAT_API_URL || "/api/chat";
  const response = await fetch(`${chatUrl.replace(/\/$/, "")}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: question, session_id: sessionId }),
    signal: AbortSignal.timeout(180_000),
  });
  if (!response.ok) {
    throw new Error(`The chat service returned HTTP ${response.status}.`);
  }
  if (!response.body) {
    throw new Error("The chat service did not provide a response stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamedResponse = "";
  let returnedSessionId = "";
  let completed = false;

  function processFrame(frame: string) {
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of frame.replace(/\r/g, "").split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (dataLines.length === 0) return;

    const payload: unknown = JSON.parse(dataLines.join("\n"));
    if (!payload || typeof payload !== "object") {
      throw new Error("The chat service sent an invalid stream event.");
    }
    const values = payload as Record<string, unknown>;
    if (eventName === "status" && typeof values.message === "string") {
      onStatus(values.message);
    } else if (eventName === "delta" && typeof values.text === "string") {
      streamedResponse += values.text;
      onText(values.text);
    } else if (eventName === "done" && typeof values.session_id === "string") {
      returnedSessionId = values.session_id;
      completed = true;
    } else if (eventName === "error") {
      throw new Error(
        typeof values.message === "string"
          ? values.message
          : "The assistant could not complete this request.",
      );
    }
  }

  while (true) {
    const { value, done } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: !done });
    if (done) buffer += decoder.decode();

    let frameBoundary = buffer.indexOf("\n\n");
    while (frameBoundary !== -1) {
      processFrame(buffer.slice(0, frameBoundary));
      buffer = buffer.slice(frameBoundary + 2);
      frameBoundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }

  if (buffer.trim()) processFrame(buffer);
  if (!completed || !returnedSessionId) {
    throw new Error("The assistant stream ended before the request completed.");
  }
  return { response: streamedResponse, sessionId: returnedSessionId };
}

function ChatbotAnimation() {
  return (
    <DotLottieReact
      src="/animations/chatbot_header.lottie"
      loop
      autoplay
      aria-label="Assistant is replying"
      renderConfig={{ autoResize: true, devicePixelRatio: 2 }}
    />
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [responseStarted, setResponseStarted] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  function newChat() {
    const newSessionId = window.crypto.randomUUID();
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, newSessionId);
    setSessionId(newSessionId);
    setMessages([]);
    setInput("");
    setLoading(false);
    setResponseStarted(false);
    setMobileSidebarOpen(false);
  }

  async function sendMessage(text?: string) {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    const activeSessionId =
      sessionId ??
      window.sessionStorage.getItem(SESSION_STORAGE_KEY) ??
      window.crypto.randomUUID();
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, activeSessionId);
    setSessionId(activeSessionId);
    setMessages((previous) => [
      ...previous,
      { id: window.crypto.randomUUID(), role: "user", content: question },
    ]);
    setInput("");
    setResponseStarted(false);
    setLoading(true);
    const assistantId = window.crypto.randomUUID();
    try {
      const answer = await streamAssistantResponse(
        question,
        activeSessionId,
        (text) => {
          setResponseStarted(true);
          setMessages((previous) => {
            const existing = previous.some((message) => message.id === assistantId);
            return existing
              ? previous.map((message) =>
                  message.id === assistantId
                    ? { ...message, content: message.content + text }
                    : message,
                )
              : [...previous, { id: assistantId, role: "assistant", content: text }];
          });
        },
        () => {},
      );
      window.sessionStorage.setItem(SESSION_STORAGE_KEY, answer.sessionId);
      setSessionId(answer.sessionId);
      if (!answer.response) {
        setMessages((previous) => [
          ...previous,
          {
            id: assistantId,
            role: "assistant",
            content: "The assistant completed without returning a text response.",
          },
        ]);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "The assistant request failed.";
      setMessages((previous) => {
        const existing = previous.some((item) => item.id === assistantId);
        return existing
          ? previous.map((item) =>
              item.id === assistantId
                ? { ...item, content: `${item.content}\n\n${message}` }
                : item,
            )
          : [...previous, { id: assistantId, role: "assistant", content: message }];
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <div className="ambient ambient-one" /><div className="ambient ambient-two" />
      <AnimatePresence>{mobileSidebarOpen && <motion.div className="mobile-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileSidebarOpen(false)} />}</AnimatePresence>

      <motion.aside className={`sidebar ${sidebarOpen ? "sidebar-expanded" : "sidebar-collapsed"} ${mobileSidebarOpen ? "mobile-sidebar-open" : ""}`} animate={{ width: sidebarOpen ? 268 : 76 }} transition={{ duration: 0.25, ease: "easeInOut" }}>
        <div className="sidebar-top">
          <div className="brand"><div className="brand-icon" aria-hidden="true" />{sidebarOpen && <div className="brand-copy"><span className="brand-name">Academic Chatbot</span></div>}</div>
          <button className="icon-button collapse-button" aria-label="Toggle sidebar" onClick={() => { setSidebarOpen(!sidebarOpen); setMobileSidebarOpen(false); }}>{sidebarOpen ? <PanelLeftClose size={18} /> : <Menu size={18} />}</button>
        </div>
        <button className="new-chat-button" onClick={newChat} disabled={loading}><Plus size={19} />{sidebarOpen && <span>New conversation</span>}</button>
        {sidebarOpen && <div className="sidebar-content"><div className="sidebar-bottom"><div className="help-card"><div className="help-card-icon"><ShieldCheck size={19} /></div><div><strong>Academic answers</strong><p>Grounded in official documents</p></div></div></div></div>}
      </motion.aside>

      <section className="main-panel">
        <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMobileSidebarOpen(true)}><Menu size={20} /></button><div className="breadcrumb"><strong>Academic Chatbot</strong></div></div></header>
        <div className="chat-scroll-area">
          <AnimatePresence mode="wait">
            {messages.length === 0 ? <motion.div key="welcome" className="welcome-screen" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }}><h1 className="welcome-title">Academic Chatbot</h1><p className="welcome-description">Ask questions about courses, exams, academic rules, and more.</p><div className="suggestion-grid">{suggestions.map((item, index) => { const Icon = item.icon; return <motion.button key={item.title} className="suggestion-card" onClick={() => void sendMessage(item.text)} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 + index * 0.09, duration: 0.35 }} whileHover={{ y: -4, scale: 1.01 }} whileTap={{ scale: 0.98 }}><div className={`suggestion-icon ${item.color}`}><Icon size={20} /></div><div className="suggestion-copy"><strong>{item.title}</strong><span>{item.text}</span></div><span className="suggestion-arrow">&rarr;</span></motion.button>; })}</div></motion.div> : <motion.div key="conversation" className="conversation" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>{messages.map((message, index) => <motion.div key={message.id} className={`message-row ${message.role === "user" ? "user-row" : "assistant-row"}`} initial={{ opacity: 0, y: 12, scale: 0.99 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.25, delay: index === messages.length - 1 ? 0 : 0.02 }}>{message.role === "assistant" && <div className="assistant-avatar"><ChatbotAnimation /></div>}<div className="message-content">{message.role === "assistant" && <div className="message-author">Academic Chatbot</div>}<div className={`message-bubble ${message.role === "user" ? "user-bubble" : "assistant-bubble"}`}>{message.content}</div></div></motion.div>)}{loading && !responseStarted && <motion.div className="message-row assistant-row" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}><div className="typing-bubble" role="status" aria-label="Assistant is typing"><span /><span /><span /></div></motion.div>}</motion.div>}
          </AnimatePresence>
        </div>
        <div className="composer-area"><form className="composer" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}><textarea rows={1} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder="Ask about courses, exams, or academic rules..." aria-label="Your message" disabled={loading} /><div className="composer-footer"><div className="composer-hint"><Sparkles size={14} /><span>Academic answers, made simple</span></div><motion.button type="submit" className="send-button" disabled={!input.trim() || loading} aria-label="Send message" whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.92 }}><ArrowUp size={19} /></motion.button></div></form><p className="disclaimer">Responses appear here when the academic service is connected.</p></div>
      </section>
    </main>
  );
}
