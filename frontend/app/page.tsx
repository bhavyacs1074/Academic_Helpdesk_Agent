"use client";

import { useState } from "react";
import { DotLottieReact } from "@lottiefiles/dotlottie-react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, BookOpen, CalendarDays, FileText, Menu, PanelLeftClose, Plus, ShieldCheck, Sparkles } from "lucide-react";

type Message = { id: number; role: "user" | "assistant"; content: string };

const suggestions = [
  { icon: BookOpen, title: "Academic regulations", text: "What are the attendance requirements?", color: "violet" },
  { icon: CalendarDays, title: "Course information", text: "How do I find my course slot?", color: "blue" },
  { icon: FileText, title: "Email assistant", text: "Draft a sick-leave email to my professor.", color: "pink" },
];

async function requestAssistantResponse(question: string): Promise<string | null> {
  try {
    const response = await fetch(process.env.NEXT_PUBLIC_CHAT_API_URL || "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });
    if (!response.ok) return null;
    const data: unknown = await response.json();
    if (typeof data === "string") return data.trim() || null;
    if (!data || typeof data !== "object") return null;
    const result = data as Record<string, unknown>;
    for (const key of ["response", "answer", "message", "content"]) {
      if (typeof result[key] === "string" && result[key].trim()) return result[key].trim();
    }
    return null;
  } catch {
    return null;
  }
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
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  function newChat() {
    setMessages([]);
    setInput("");
    setLoading(false);
    setMobileSidebarOpen(false);
  }

  async function sendMessage(text?: string) {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    setMessages((previous) => [...previous, { id: Date.now(), role: "user", content: question }]);
    setInput("");
    setLoading(true);
    const answer = await requestAssistantResponse(question);
    setMessages((previous) => [
      ...previous,
      {
        id: Date.now() + 1,
        role: "assistant",
        content: answer ?? "I couldn't respond to this query right now. Please try again later.",
      },
    ]);
    setLoading(false);
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
        <button className="new-chat-button" onClick={newChat}><Plus size={19} />{sidebarOpen && <span>New conversation</span>}</button>
        {sidebarOpen && <div className="sidebar-content"><div className="sidebar-bottom"><div className="help-card"><div className="help-card-icon"><ShieldCheck size={19} /></div><div><strong>Academic answers</strong><p>Grounded in official documents</p></div></div></div></div>}
      </motion.aside>

      <section className="main-panel">
        <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMobileSidebarOpen(true)}><Menu size={20} /></button><div className="breadcrumb"><strong>Academic Chatbot</strong></div></div></header>
        <div className="chat-scroll-area">
          <AnimatePresence mode="wait">
            {messages.length === 0 ? <motion.div key="welcome" className="welcome-screen" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }}><h1 className="welcome-title">Academic Chatbot</h1><p className="welcome-description">Ask questions about courses, exams, academic rules, and more.</p><div className="suggestion-grid">{suggestions.map((item, index) => { const Icon = item.icon; return <motion.button key={item.title} className="suggestion-card" onClick={() => void sendMessage(item.text)} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 + index * 0.09, duration: 0.35 }} whileHover={{ y: -4, scale: 1.01 }} whileTap={{ scale: 0.98 }}><div className={`suggestion-icon ${item.color}`}><Icon size={20} /></div><div className="suggestion-copy"><strong>{item.title}</strong><span>{item.text}</span></div><span className="suggestion-arrow">&rarr;</span></motion.button>; })}</div></motion.div> : <motion.div key="conversation" className="conversation" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>{messages.map((message, index) => <motion.div key={message.id} className={`message-row ${message.role === "user" ? "user-row" : "assistant-row"}`} initial={{ opacity: 0, y: 12, scale: 0.99 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.25, delay: index === messages.length - 1 ? 0 : 0.02 }}>{message.role === "assistant" && <div className="assistant-avatar"><ChatbotAnimation /></div>}<div className="message-content">{message.role === "assistant" && <div className="message-author">Academic Chatbot</div>}<div className={`message-bubble ${message.role === "user" ? "user-bubble" : "assistant-bubble"}`}>{message.content}</div></div></motion.div>)}{loading && <motion.div className="message-row assistant-row" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}><div className="assistant-avatar"><ChatbotAnimation /></div><div className="typing-bubble"><span className="typing-label">Replying</span></div></motion.div>}</motion.div>}
          </AnimatePresence>
        </div>
        <div className="composer-area"><form className="composer" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}><textarea rows={1} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder="Ask about courses, exams, or academic rules..." aria-label="Your message" disabled={loading} /><div className="composer-footer"><div className="composer-hint"><Sparkles size={14} /><span>Academic answers, made simple</span></div><motion.button type="submit" className="send-button" disabled={!input.trim() || loading} aria-label="Send message" whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.92 }}><ArrowUp size={19} /></motion.button></div></form><p className="disclaimer">Responses appear here when the academic service is connected.</p></div>
      </section>
    </main>
  );
}
