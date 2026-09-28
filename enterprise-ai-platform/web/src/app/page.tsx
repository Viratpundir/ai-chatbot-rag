"use client";

import {
  Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpenCheck, Bot,
  Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Clock3,
  FilePlus2, FileText, Files, Gauge, History, LayoutDashboard, LoaderCircle,
  LogOut, Menu, MessageCircle, MessageSquareText, Paperclip, Plus, Search,
  Send, ShieldCheck, Sparkles, Trash2, Upload, Users, X, type LucideIcon,
} from "lucide-react";
import { memo, useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  api, clearSession, downloadDocument, listDocuments, saveSession, streamApi, type AdminStats, type ChatResult,
  type Citation, type ConversationDetail, type ConversationSummary,
  type CurrentUser, type DocumentRecord, type SystemHealth,
} from "@/lib/api";
import { AppearanceMenu, ThemeToggle } from "@/components/theme-provider";

type View = "Dashboard" | "Documents" | "AI Chat" | "AI Guide" | "History" | "Admin";
type ChatLine = { id: string; role: "user" | "assistant"; content: string; citations?: Citation[]; retryQuestion?: string };
type NavItem = { label: View; icon: LucideIcon; adminOnly?: boolean };

const navItems: NavItem[] = [
  { label: "Dashboard", icon: LayoutDashboard }, { label: "Documents", icon: Files },
  { label: "AI Chat", icon: MessageSquareText }, { label: "AI Guide", icon: BookOpenCheck },
  { label: "History", icon: History }, { label: "Admin", icon: Gauge, adminOnly: true },
];

const descriptions: Record<View, string> = {
  Dashboard: "Your organisation's knowledge, in one place.",
  Documents: "Manage the files available to your workspace.",
  "AI Chat": "Ask questions and trace every answer to its source.",
  "AI Guide": "Get guided help grounded in your organisation's knowledge.",
  History: "Pick up a previous conversation where you left off.",
  Admin: "Platform activity, usage and service health.",
};

function formatDate(value?: string | null) {
  if (!value) return "Just now";
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function formatBytes(bytes?: number | null) {
  if (!bytes) return "—";
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function initials(name: string) {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "U";
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status.toLowerCase()}`}>{status.replaceAll("_", " ")}</span>;
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return <div className="citation-list">{citations.map((citation) => <details className="citation" key={`${citation.document_id}-${citation.index}`}><summary><FileText size={14} /><span>{citation.filename}</span>{citation.page ? <small>p. {citation.page}</small> : null}<ChevronDown size={14} /></summary><p>{citation.excerpt}</p>{citation.section ? <small>{citation.section}</small> : null}</details>)}</div>;
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (user: CurrentUser) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [selectedRole, setSelectedRole] = useState<"EMPLOYEE" | "ADMIN">("EMPLOYEE");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(null);
    try {
      if (mode === "register") {
        const result = await api<{ message: string }>("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ name, email, password, role: "EMPLOYEE" }) });
        setMode("login"); setMessage({ text: result.message, error: false });
      } else {
        const tokens = await api<{ access_token: string; refresh_token: string }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
        saveSession(tokens.access_token, tokens.refresh_token);
        const profile = await api<CurrentUser>("/api/v1/auth/me");
        const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(profile.role.toUpperCase());
        if (selectedRole === "ADMIN" && !isAdmin) {
          await api("/api/v1/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: tokens.refresh_token }) }).catch(() => undefined);
          clearSession();
          setMessage({ text: "This account does not have administrator access.", error: true });
          return;
        }
        onAuthenticated(profile);
      }
    } catch (error) {
      if (mode === "login") clearSession();
      setMessage({ text: error instanceof Error ? error.message : "Unable to connect to the platform.", error: true });
    } finally { setBusy(false); }
  }

  return <main className="auth-screen">
    <div className="auth-art" aria-hidden="true"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-core"><Sparkles size={23} /></div><div className="art-caption"><span className="eyebrow">KNOWLEDGE, CONNECTED</span><p>Clarity lives in<br />the details.</p></div></div>
    <section className="auth-panel"><a className="brand auth-brand" href="#home"><span className="brand-mark"><Sparkles size={18} /></span><span>NexaIQ</span></a><ThemeToggle className="icon-button auth-theme-toggle" /><div className="auth-form-wrap"><span className="eyebrow">ENTERPRISE KNOWLEDGE INTELLIGENCE</span><h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1><p className="muted">{mode === "login" ? `Sign in as ${selectedRole === "ADMIN" ? "Admin" : "Employee"}.` : "Join your organisation's knowledge workspace."}</p>
      {mode === "login" ? <div className="auth-role-picker" role="group" aria-label="Sign-in role">
        <button type="button" aria-pressed={selectedRole === "EMPLOYEE"} className={selectedRole === "EMPLOYEE" ? "auth-role-option auth-role-active" : "auth-role-option"} data-testid="login-role-employee" onClick={() => { setSelectedRole("EMPLOYEE"); setMessage(null); }}>Employee</button>
        <button type="button" aria-pressed={selectedRole === "ADMIN"} className={selectedRole === "ADMIN" ? "auth-role-option auth-role-active" : "auth-role-option"} data-testid="login-role-admin" onClick={() => { setSelectedRole("ADMIN"); setMessage(null); }}>Admin</button>
      </div> : null}
      <form className="auth-form" data-testid={mode === "login" ? "login-form" : "register-form"} onSubmit={submit}>{mode === "register" ? <label>Full name<input autoComplete="name" required minLength={2} value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" /></label> : null}<label>Work email<input autoComplete="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" /></label><label>Password<input autoComplete={mode === "login" ? "current-password" : "new-password"} type="password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" /></label>
        {message ? <p className={`form-message ${message.error ? "error-message" : "success-message"}`}>{message.text}</p> : null}<button className="button button-primary auth-submit" data-testid={mode === "login" ? "login-submit" : "register-submit"} disabled={busy} type="submit">{busy ? <LoaderCircle className="spin" size={17} /> : null}{mode === "login" ? "Sign in" : "Create account"}<ArrowRight size={17} /></button>
      </form><p className="auth-switch">{mode === "login" ? "New to your workspace?" : "Already have an account?"} <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setMessage(null); }}>{mode === "login" ? "Create an account" : "Sign in"}</button></p><div className="auth-security"><ShieldCheck size={16} /><span>Protected by your organisation&apos;s access controls</span></div></div><span className="auth-version">NEXAIQ · SECURE ACCESS</span></section>
  </main>;
}

export default function Home() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [hydrating, setHydrating] = useState(true);
  const [view, setView] = useState<View>("Dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentsTotal, setDocumentsTotal] = useState(0);
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const [documentSearch, setDocumentSearch] = useState("");
  const [queryCount, setQueryCount] = useState<number | null>(null);
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [chatLines, setChatLines] = useState<ChatLine[]>([]);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const chatRequestActive = useRef(false);
  const activeChatController = useRef<AbortController | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [guideQuestion, setGuideQuestion] = useState("");
  const [guideReply, setGuideReply] = useState("");
  const [guideBusy, setGuideBusy] = useState(false);
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [historyDetail, setHistoryDetail] = useState<ConversationDetail | null>(null);
  const [adminStats, setAdminStats] = useState<AdminStats | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [adminError, setAdminError] = useState("");

  useEffect(() => {
    let active = true;
    if (!sessionStorage.getItem("access_token")) { queueMicrotask(() => { if (active) setHydrating(false); }); return () => { active = false; }; }
    api<CurrentUser>("/api/v1/auth/me").then((profile) => { if (active) setUser(profile); }).catch(() => clearSession()).finally(() => { if (active) setHydrating(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!user) return;
    let active = true;
    api<{ status: string }>("/api/v1/health").then(() => { if (active) setBackendOnline(true); }).catch(() => { if (active) setBackendOnline(false); });
    if (view === "Dashboard" || view === "Documents") {
      queueMicrotask(() => { if (active) setDocumentsBusy(true); });
      listDocuments().then((result) => { if (active) { setDocuments(result.documents); setDocumentsTotal(result.total); } }).catch((error) => { if (active) setNotice({ text: error instanceof Error ? error.message : "Documents could not be loaded.", error: true }); }).finally(() => { if (active) setDocumentsBusy(false); });
      if (view === "Dashboard") api<{ questions_asked: number }>("/api/v1/chat/stats").then((result) => { if (active) setQueryCount(result.questions_asked); }).catch(() => { if (active) setQueryCount(null); });
    }
    if (view === "History") api<{ conversations: ConversationSummary[] }>("/api/v1/chat/conversations?page=1&page_size=50").then((result) => { if (active) setHistory(result.conversations); }).catch((error) => { if (active) setNotice({ text: error instanceof Error ? error.message : "History could not be loaded.", error: true }); });
    if (view === "Admin") {
      queueMicrotask(() => { if (active) setAdminError(""); });
      Promise.all([api<AdminStats>("/api/v1/admin/dashboard"), api<SystemHealth>("/api/v1/admin/health")]).then(([stats, health]) => { if (active) { setAdminStats(stats); setSystemHealth(health); } }).catch((error) => { if (active) setAdminError(error instanceof Error ? error.message : "Admin data could not be loaded."); });
    }
    return () => { active = false; };
  }, [user, view]);

  useEffect(() => {
    if (!user || !["Dashboard", "Documents"].includes(view)) return;
    const processing = documents.some((item) => ["uploaded", "processing", "pending"].includes(item.status.toLowerCase()));
    if (!processing) return;
    const timer = window.setInterval(() => {
      void listDocuments().then((result) => {
        setDocuments(result.documents);
        setDocumentsTotal(result.total);
      }).catch((error) => {
        setNotice({ text: error instanceof Error ? error.message : "Document status could not be refreshed.", error: true });
      });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [user, view, documents]);

  async function refreshDocuments() {
    const result = await listDocuments();
    setDocuments(result.documents); setDocumentsTotal(result.total);
  }

  async function uploadFiles(files: FileList | null) {
    if (!files?.length) return;
    setUploadBusy(true); setNotice(null);
    try {
      const body = new FormData();
      for (const file of Array.from(files)) body.append("files", file);
      const accepted = await api<Array<{ document_id: string; filename: string; status: string }>>("/api/v1/documents/bulk?classification=INTERNAL", { method: "POST", body });
      const createdAt = new Date().toISOString();
      setDocuments((current) => [...accepted.map((item) => ({ document_id: item.document_id, filename: item.filename, status: item.status, classification: "INTERNAL", created_at: createdAt })), ...current]);
      await refreshDocuments(); setNotice({ text: `${files.length} ${files.length === 1 ? "document" : "documents"} uploaded. Indexing will continue in the background.` });
    } catch (error) { setNotice({ text: error instanceof Error ? error.message : "The upload could not be completed.", error: true }); }
    finally { setUploadBusy(false); }
  }

  async function deleteDocument(item: DocumentRecord) {
    if (!window.confirm(`Delete ${item.filename}? This removes it from the knowledge base.`)) return;
    setNotice(null);
    try {
      await api(`/api/v1/documents/${item.document_id}`, { method: "DELETE" });
      await refreshDocuments();
      setNotice({ text: `${item.filename} was deleted.` });
    } catch (error) {
      setNotice({ text: error instanceof Error ? error.message : "The document could not be deleted.", error: true });
    }
  }

  const runChatQuestion = useCallback(async (question: string) => {
    if (!question || chatRequestActive.current) return;
    chatRequestActive.current = true;
    const controller = new AbortController();
    activeChatController.current = controller;
    setChatBusy(true);
    setChatLines((lines) => [...lines, { id: crypto.randomUUID(), role: "user", content: question }]);

    let streamedText = "";
    let pendingText = "";
    let animationFrame = 0;
    const flushTokens = () => {
      animationFrame = 0;
      const nextText = pendingText;
      pendingText = "";
      if (!nextText) return;
      setChatLines((lines) => {
        const last = lines[lines.length - 1];
        if (last?.role === "assistant" && !last.retryQuestion) {
          return [...lines.slice(0, -1), { ...last, content: last.content + nextText }];
        }
        return [...lines, { id: crypto.randomUUID(), role: "assistant", content: nextText }];
      });
    };

    try {
      const result = await streamApi<ChatResult>(
        "/api/v1/chat/ask/stream",
        { question, conversation_id: conversationId, all_authorized: true },
        (token) => {
          streamedText += token;
          pendingText += token;
          if (!animationFrame) animationFrame = requestAnimationFrame(flushTokens);
        },
        controller.signal,
      );
      if (animationFrame) cancelAnimationFrame(animationFrame);
      pendingText = "";
      setConversationId(result.conversation_id);
      setChatLines((lines) => {
        const last = lines[lines.length - 1];
        if (last?.role === "assistant" && !last.retryQuestion) {
          return [...lines.slice(0, -1), { ...last, content: result.answer, citations: result.citations }];
        }
        return [...lines, { id: crypto.randomUUID(), role: "assistant", content: result.answer, citations: result.citations }];
      });
    } catch (error) {
      if (animationFrame) cancelAnimationFrame(animationFrame);
      if (controller.signal.aborted) return;
      const message = error instanceof Error ? error.message : "Something went wrong while processing your question. Please try again.";
      setChatLines((lines) => {
        const last = lines[lines.length - 1];
        if (last?.role === "assistant" && !last.retryQuestion) {
          return [...lines.slice(0, -1), {
            ...last,
            content: streamedText || message,
            retryQuestion: question,
          }];
        }
        return [...lines, { id: crypto.randomUUID(), role: "assistant", content: message, retryQuestion: question }];
      });
    } finally {
      chatRequestActive.current = false;
      activeChatController.current = null;
      setChatBusy(false);
    }
  }, [conversationId]);

  const retryChatQuestion = useCallback((question: string) => {
    void runChatQuestion(question);
  }, [runChatQuestion]);

  async function sendChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = chatQuestion.trim();
    if (!question || chatRequestActive.current) return;
    setChatQuestion("");
    await runChatQuestion(question);
  }

  async function sendGuide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const message = guideQuestion.trim();
    if (!message || guideBusy) return;
    setGuideQuestion(""); setGuideReply(""); setGuideBusy(true);
    try { const result = await api<{ reply: string }>("/api/v1/chat/agent", { method: "POST", body: JSON.stringify({ message, all_authorized: true }) }); const reply = typeof result?.reply === "string" ? result.reply.trim() : ""; if (!reply) throw new Error("The AI Guide returned an empty response. Please try again."); setGuideReply(reply); }
    catch (error) { setGuideReply(error instanceof TypeError ? "The knowledge service is temporarily unavailable. Please try again." : error instanceof Error ? error.message : "The guide could not respond. Please try again."); }
    finally { setGuideBusy(false); }
  }

  async function openConversation(item: ConversationSummary) {
    try { setHistoryDetail(await api<ConversationDetail>(`/api/v1/chat/conversations/${item.conversation_id}`)); }
    catch (error) { setNotice({ text: error instanceof Error ? error.message : "Conversation could not be opened.", error: true }); }
  }

  async function signOut() {
    activeChatController.current?.abort();
    const refreshToken = sessionStorage.getItem("refresh_token");
    if (refreshToken) { try { await api("/api/v1/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) }); } catch { /* Complete local sign-out if the service is unavailable. */ } }
    clearSession(); setUser(null); setView("Dashboard"); setChatLines([]); setConversationId(null);
  }

  if (hydrating) return <main className="boot-screen"><span className="brand-mark"><Sparkles size={18} /></span><LoaderCircle className="spin" size={20} /></main>;
  if (!user) return <AuthScreen onAuthenticated={setUser} />;

  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user.role.toUpperCase());
  const filteredDocuments = documents.filter((item) => item.filename.toLowerCase().includes(documentSearch.toLowerCase()));
  const readyDocuments = documents.filter((item) => item.status.toLowerCase() === "ready").length;
  const processingDocuments = documents.filter((item) => ["uploaded", "processing", "pending"].includes(item.status.toLowerCase())).length;
  const pageTitle = view === "Admin" ? "Admin dashboard" : view;

  return <div className="workspace">
    {sidebarOpen ? <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} /> : null}
    <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-head"><a className="brand" href="#home"><span className="brand-mark"><Sparkles size={17} /></span><span>NexaIQ</span></a><button className="icon-button sidebar-close" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}><X size={18} /></button></div>
      <div className="workspace-switch"><span className="workspace-avatar">K</span><span className="workspace-label"><strong>Knowledge workspace</strong><small>Enterprise intelligence</small></span></div>
      <span className="nav-caption">WORKSPACE</span><nav className="main-nav" aria-label="Main navigation">
        {navItems.filter((item) => !item.adminOnly || isAdmin).map(({ label, icon: Icon }) => <button key={label} className={`nav-link ${view === label ? "nav-active" : ""}`} data-testid={label === "Admin" ? "admin-dashboard-button" : undefined} onClick={() => { setSidebarOpen(false); if (label === "Admin") router.push("/admin"); else setView(label); }}><Icon size={18} /><span>{label === "Admin" ? "Admin dashboard" : label}</span>{label === "Documents" && documentsTotal > 0 ? <small>{documentsTotal}</small> : null}</button>)}
      </nav>
      <div className="sidebar-spacer" /><div className="sidebar-help"><div className="help-icon"><CircleHelp size={18} /></div><strong>Need a hand?</strong><p>Your knowledge guide can walk you through common tasks.</p><button onClick={() => setView("AI Guide")}>Open AI Guide<ArrowRight size={14} /></button></div>
      <div className="sidebar-bottom"><span className="engine-dot" /><span>Knowledge engine</span><span className="engine-version">v1.0</span></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Menu size={20} /></button><span className="crumb-root">Workspace</span><ChevronRight size={14} /><span className="crumb-current">{pageTitle}</span></div><div className="topbar-right"><span className={`backend-indicator ${backendOnline === false ? "offline" : ""}`} data-testid="backend-status"><span />{backendOnline === null ? "Checking services" : backendOnline ? "Backend online" : "Backend offline"}</span><AppearanceMenu className="icon-button theme-toggle" /><button className="icon-button top-help" title="Open AI Guide" aria-label="Open AI Guide" onClick={() => setView("AI Guide")}><CircleHelp size={18} /></button><button className="profile-button" data-testid="logout-button" onClick={signOut} title="Sign out"><span className="avatar">{initials(user.name)}</span><span className="profile-copy"><strong>{user.name}</strong><small>{user.role.replaceAll("_", " ")}</small></span><LogOut size={15} /></button></div></header>
      <div className="content-wrap">
        <div className="page-heading"><div><span className="eyebrow">{view === "Dashboard" ? "YOUR KNOWLEDGE SPACE" : "NEXAIQ WORKSPACE"}</span><h1>{view === "Dashboard" ? `Welcome back, ${user.name.split(" ")[0]}` : pageTitle}</h1><p>{descriptions[view]}</p></div>{view === "Documents" ? <label className="button button-primary upload-button" data-testid="document-upload-button"><Upload size={16} />{uploadBusy ? "Uploading" : "Upload documents"}<input type="file" multiple accept=".pdf,.docx,.txt,.md,.html" disabled={uploadBusy} onChange={(event) => { void uploadFiles(event.target.files); event.currentTarget.value = ""; }} /></label> : null}</div>
        {notice ? <div className={`notice ${notice.error ? "notice-error" : "notice-success"}`}><span>{notice.error ? <CircleHelp size={17} /> : <CheckCircle2 size={17} />}{notice.text}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice(null)}><X size={16} /></button></div> : null}
        {view === "Dashboard" ? <DashboardView documents={documents} total={documentsTotal} busy={documentsBusy} ready={readyDocuments} processing={processingDocuments} queries={queryCount} onNavigate={setView} onUpload={uploadFiles} uploadBusy={uploadBusy} /> : null}
        {view === "Documents" ? <DocumentsView documents={filteredDocuments} total={documentsTotal} busy={documentsBusy} search={documentSearch} setSearch={setDocumentSearch} onUpload={uploadFiles} onDelete={deleteDocument} uploadBusy={uploadBusy} /> : null}
        {view === "AI Chat" ? <ChatView lines={chatLines} question={chatQuestion} setQuestion={setChatQuestion} busy={chatBusy} conversationId={conversationId} onSubmit={sendChat} onRetry={retryChatQuestion} onNew={() => { setChatLines([]); setConversationId(null); }} /> : null}
        {view === "AI Guide" ? <GuideView question={guideQuestion} setQuestion={setGuideQuestion} reply={guideReply} busy={guideBusy} onSubmit={sendGuide} /> : null}
        {view === "History" ? <HistoryView history={history} detail={historyDetail} onOpen={openConversation} onClose={() => setHistoryDetail(null)} /> : null}
        {view === "Admin" ? <AdminView stats={adminStats} health={systemHealth} error={adminError} /> : null}
        <footer className="page-footer"><span>NEXAIQ · ENTERPRISE KNOWLEDGE INTELLIGENCE PLATFORM</span><span>Access follows your organisation&apos;s permissions</span></footer>
      </div>
    </main>
  </div>;
}

function Metric({ icon: Icon, label, value, note, tone }: { icon: LucideIcon; label: string; value: string; note: string; tone: string }) {
  return <article className="metric-card"><span className={`metric-icon metric-${tone}`}><Icon size={18} /></span><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong><span className="metric-note">{note}</span></article>;
}

function DashboardView({ documents, total, busy, ready, processing, queries, onNavigate, onUpload, uploadBusy }: { documents: DocumentRecord[]; total: number; busy: boolean; ready: number; processing: number; queries: number | null; onNavigate: (view: View) => void; onUpload: (files: FileList | null) => Promise<void>; uploadBusy: boolean }) {
  const readyPercent = total ? Math.round((ready / total) * 100) : 0;
  return <>
    <section className="metric-grid"><Metric icon={Files} label="Documents" value={busy ? "—" : total.toLocaleString()} note="In your workspace" tone="violet" /><Metric icon={CheckCircle2} label="Ready to search" value={busy ? "—" : ready.toLocaleString()} note={total ? `${readyPercent}% of your library` : "Upload your first file"} tone="mint" /><Metric icon={MessageCircle} label="Questions asked" value={queries === null ? "—" : queries.toLocaleString()} note="Across your conversations" tone="coral" /><Metric icon={Activity} label="Being indexed" value={busy ? "—" : processing.toLocaleString()} note="Processing in background" tone="blue" /></section>
    <section className="dashboard-grid"><div className="panel getting-started"><div className="panel-heading"><div><span className="eyebrow">A GOOD PLACE TO START</span><h2>Put your knowledge to work</h2></div><span className="heading-spark"><Sparkles size={18} /></span></div><div className="start-grid">
      <label className="start-card start-upload"><span className="start-icon"><FilePlus2 size={19} /></span><span><strong>{uploadBusy ? "Uploading files" : "Add documents"}</strong><small>Bring policies, reports and guides into your workspace.</small></span><ArrowUpRight size={16} /><input id="dashboard-upload" className="visually-hidden" type="file" multiple accept=".pdf,.docx,.txt,.md,.html" disabled={uploadBusy} onChange={(event) => { void onUpload(event.target.files); event.currentTarget.value = ""; }} /></label>
      <button className="start-card start-chat" onClick={() => onNavigate("AI Chat")}><span className="start-icon"><MessageSquareText size={19} /></span><span><strong>Ask your documents</strong><small>Get grounded answers with page-level sources.</small></span><ArrowUpRight size={16} /></button>
      <button className="start-card start-guide" onClick={() => onNavigate("AI Guide")}><span className="start-icon"><BookOpenCheck size={19} /></span><span><strong>Open AI Guide</strong><small>Work through a process with contextual intelligence.</small></span><ArrowUpRight size={16} /></button>
    </div></div><div className="panel library-panel"><div className="panel-heading"><div><span className="eyebrow">LIBRARY STATUS</span><h2>Searchable knowledge</h2></div><span className="status-orbit"><span /></span></div><div className="library-number">{busy ? "—" : ready}<span> / {busy ? "—" : total} documents</span></div><div className="progress-track"><span style={{ width: `${readyPercent}%` }} /></div><div className="library-legend"><span><i className="legend-ready" />Ready <b>{busy ? "—" : ready}</b></span><span><i className="legend-processing" />Processing <b>{busy ? "—" : processing}</b></span></div><button className="text-button" onClick={() => onNavigate("Documents")}>View document library<ArrowRight size={15} /></button></div></section>
    <section className="panel recent-panel"><div className="panel-heading"><div><span className="eyebrow">YOUR LIBRARY</span><h2>Recent documents</h2></div><button className="text-button" onClick={() => onNavigate("Documents")}>View all<ArrowRight size={15} /></button></div>{busy ? <div className="empty-inline"><LoaderCircle className="spin" size={18} />Loading documents…</div> : documents.length ? <div className="document-list">{documents.slice(0, 5).map((item) => <DocumentRow key={item.document_id} document={item} compact />)}</div> : <EmptyState icon={Files} title="Your library is ready" text="Upload a document to make it searchable in chat." action={<label className="button button-secondary"><Plus size={16} />Add first document<input type="file" multiple accept=".pdf,.docx,.txt,.md,.html" disabled={uploadBusy} onChange={(event) => { void onUpload(event.target.files); event.currentTarget.value = ""; }} /></label>} />}</section>
  </>;
}

function DocumentsView({ documents, total, busy, search, setSearch, onUpload, onDelete, uploadBusy }: { documents: DocumentRecord[]; total: number; busy: boolean; search: string; setSearch: (value: string) => void; onUpload: (files: FileList | null) => Promise<void>; onDelete: (document: DocumentRecord) => Promise<void>; uploadBusy: boolean }) {
  return <section className="panel documents-panel" data-testid="documents-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void onUpload(event.dataTransfer.files); }}><div className="document-toolbar"><div className="table-count"><strong>{total}</strong> {total === 1 ? "document" : "documents"}</div><label className="search-field"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a document" aria-label="Find a document" />{search ? <button className="icon-button" aria-label="Clear search" onClick={() => setSearch("")}><X size={14} /></button> : null}</label><label className="button button-secondary compact-upload"><Upload size={15} />Upload<input type="file" multiple accept=".pdf,.docx,.txt,.md,.html" disabled={uploadBusy} onChange={(event) => { void onUpload(event.target.files); event.currentTarget.value = ""; }} /></label></div>
    {busy ? <div className="empty-inline"><LoaderCircle className="spin" size={18} />Loading your library…</div> : documents.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>DOCUMENT</th><th>STATUS</th><th>CLASSIFICATION</th><th>SIZE</th><th>ADDED</th><th aria-label="Actions" /></tr></thead><tbody>{documents.map((item) => <tr key={item.document_id}><td><div className="file-cell"><span className="file-icon"><FileText size={17} /></span><span><strong>{item.filename}</strong><small>{item.page_count ? `${item.page_count} pages` : item.department || "Knowledge document"}</small></span></div></td><td><StatusPill status={item.status} />{item.error_message ? <span className="inline-error" title={item.error_message}>Needs attention</span> : null}</td><td><span className="classification">{item.classification}</span></td><td>{formatBytes(item.file_size)}</td><td>{formatDate(item.created_at)}</td><td><div className="admin-actions"><button className="icon-button row-action" aria-label={`Download ${item.filename}`} title="Download" onClick={() => { void downloadDocument(item.document_id, item.filename).catch((error) => window.alert(error instanceof Error ? error.message : "Download failed")); }}><ArrowDownToLine size={16} /></button><button className="icon-button row-action admin-delete-action" data-testid="document-delete-button" aria-label={`Delete ${item.filename}`} title="Delete" onClick={() => { void onDelete(item); }}><Trash2 size={16} /></button></div></td></tr>)}</tbody></table></div> : <EmptyState icon={Files} title={search ? "No matching documents" : "No documents yet"} text={search ? "Try a different search term." : "Upload policies, reports or guides to make them searchable."} action={!search ? <label className="button button-primary"><Upload size={16} />Upload documents<input type="file" multiple accept=".pdf,.docx,.txt,.md,.html" disabled={uploadBusy} onChange={(event) => { void onUpload(event.target.files); event.currentTarget.value = ""; }} /></label> : null} />}
  </section>;
}

function DocumentRow({ document: item, compact = false }: { document: DocumentRecord; compact?: boolean }) {
  return <div className={`document-row ${compact ? "document-row-compact" : ""}`}><span className="file-icon"><FileText size={17} /></span><span className="document-name"><strong>{item.filename}</strong><small>{formatBytes(item.file_size)}{item.page_count ? ` · ${item.page_count} pages` : ""}</small></span><StatusPill status={item.status} /><span className="document-date">{formatDate(item.created_at)}</span></div>;
}

const ChatMessage = memo(function ChatMessage({ line, onRetry }: {
  line: ChatLine;
  onRetry: (question: string) => void;
}) {
  return (
    <article className={`chat-message message-${line.role}`}>
      <span className={`message-avatar ${line.role === "assistant" ? "assistant-avatar" : "user-avatar"}`}>
        {line.role === "assistant" ? <Sparkles size={15} /> : "You"}
      </span>
      <div className="message-body">
        <span className="message-byline">
          {line.role === "assistant" ? "NexaIQ" : "You"}
          <small>{line.role === "assistant" ? "KNOWLEDGE ASSISTANT" : ""}</small>
        </span>
        <p>{line.content}</p>
        {line.retryQuestion ? <small className="inline-error">The response did not complete.</small> : null}
        {line.citations ? <CitationList citations={line.citations} /> : null}
        {line.retryQuestion ? <button type="button" className="text-button" onClick={() => onRetry(line.retryQuestion!)}>Retry response<ArrowRight size={14} /></button> : null}
      </div>
    </article>
  );
});

function ChatView({ lines, question, setQuestion, busy, conversationId, onSubmit, onRetry, onNew }: {
  lines: ChatLine[];
  question: string;
  setQuestion: (value: string) => void;
  busy: boolean;
  conversationId: string | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onRetry: (question: string) => void;
  onNew: () => void;
}) {
  return (
    <section className="chat-layout">
      <div className="chat-main panel">
        <div className="chat-toolbar">
          <div className="scope-label"><span className="scope-check"><Check size={12} /></span><span><strong>All accessible documents</strong><small>Answers are grounded in your permitted library</small></span><ChevronDown size={15} /></div>
          <button className="button button-secondary new-chat" disabled={busy} onClick={onNew}><Plus size={15} />New chat</button>
        </div>
        <div className={`chat-transcript ${lines.length ? "has-messages" : ""}`}>
          {lines.length ? lines.map((line) => (
            <ChatMessage key={line.id} line={line} onRetry={onRetry} />
          )) : (
            <div className="chat-welcome">
              <span className="welcome-mark"><Sparkles size={22} /></span><span className="eyebrow">YOUR KNOWLEDGE, IN CONTEXT</span>
              <h2>What would you like to know?</h2>
              <p>Ask a question about your documents. Answers include the source passages they came from.</p>
              <div className="prompt-suggestions">
                <button onClick={() => setQuestion("What are the key policies I should know about?")}><span>01</span>Summarise our key policies<ArrowRight size={14} /></button>
                <button onClick={() => setQuestion("What are the main findings in the latest report?")}><span>02</span>Find key points in a report<ArrowRight size={14} /></button>
                <button onClick={() => setQuestion("What does the employee handbook say about leave?")}><span>03</span>Look up a specific process<ArrowRight size={14} /></button>
              </div>
            </div>
          )}
          {busy && lines[lines.length - 1]?.role !== "assistant" ? <article className="chat-message message-assistant"><span className="message-avatar assistant-avatar"><Sparkles size={15} /></span><div className="message-body"><span className="message-byline">NexaIQ<small>SEARCHING YOUR KNOWLEDGE</small></span><div className="thinking-indicator"><i /><i /><i /></div></div></article> : null}
        </div>
        <form className="chat-composer" onSubmit={onSubmit}>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Ask a question about your documents…" rows={2} maxLength={4000} />
          <div className="composer-actions"><span><Paperclip size={15} />{conversationId ? "Conversation saved to history" : "Search is limited to documents you can access"}</span><button type="submit" className="send-button" data-testid="chat-send-button" disabled={!question.trim() || busy} aria-label="Send question"><Send size={17} /></button></div>
        </form>
      </div>
      <aside className="chat-aside">
        <div className="aside-card citation-note"><span className="aside-icon"><ShieldCheck size={18} /></span><h3>Grounded in your sources</h3><p>Answers are retrieved from documents you are authorised to see. Open a citation to inspect the source excerpt.</p><div className="aside-divider" /><span className="aside-foot"><CheckCircle2 size={14} />Document permissions enforced</span></div>
        <div className="aside-card"><span className="eyebrow">HOW IT WORKS</span>{[["01", "Ask naturally", "Use the language you would use with a colleague."], ["02", "Sources are retrieved", "Relevant passages are ranked from your library."], ["03", "Verify the answer", "Review citations beside every response."]].map(([number, title, text]) => <div className="workflow-step" key={number}><span>{number}</span><p><strong>{title}</strong><small>{text}</small></p></div>)}</div>
      </aside>
    </section>
  );
}

function GuideView({ question, setQuestion, reply, busy, onSubmit }: { question: string; setQuestion: (value: string) => void; reply: string; busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const prompts = ["Walk me through our document approval process", "What should I review before an audit?", "Help me find the right policy"];
  return <section className="guide-layout"><div className="guide-intro"><div className="guide-art"><div className="guide-ring ring-a" /><div className="guide-ring ring-b" /><span><Bot size={31} /></span><i className="guide-spark spark-a"><Sparkles size={13} /></i><i className="guide-spark spark-b"><Check size={12} /></i></div><span className="eyebrow">CONTEXTUAL INTELLIGENCE</span><h2>A capable guide<br />for complex work.</h2><p>Describe what you are trying to do. The guide can connect the steps to the policies and documents your organisation has made available.</p><div className="guide-capabilities"><span><CheckCircle2 size={15} />Context-aware</span><span><ShieldCheck size={15} />Permission-checked</span><span><FileText size={15} />Source-informed</span></div></div><div className="guide-workspace panel"><div className="guide-conversation-head"><span className="guide-status"><i />READY WHEN YOU ARE</span><span className="guide-label"><Sparkles size={15} />AI GUIDE</span></div>
    {reply || busy ? <div className="guide-response"><span className="message-avatar assistant-avatar"><Sparkles size={15} /></span><div><span className="message-byline">NexaIQ Guide<small>CONTEXTUAL ASSISTANT</small></span>{busy ? <div className="thinking-indicator"><i /><i /><i /></div> : <p>{reply}</p>}</div></div> : <div className="guide-empty"><span className="eyebrow">START WITH A TASK</span><h3>What are you working through?</h3><p>Try one of these, or describe your task in your own words.</p><div className="guide-prompts">{prompts.map((prompt) => <button key={prompt} onClick={() => setQuestion(prompt)}>{prompt}<ArrowUpRight size={15} /></button>)}</div></div>}
    <form className="guide-composer" onSubmit={onSubmit}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Describe the task you need help with…" rows={2} maxLength={4000} /><div><span>Responses use your permitted knowledge base</span><button className="button button-primary" type="submit" data-testid="guide-submit-button" disabled={!question.trim() || busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />}Send to guide</button></div></form></div></section>;
}

function HistoryView({ history, detail, onOpen, onClose }: { history: ConversationSummary[]; detail: ConversationDetail | null; onOpen: (item: ConversationSummary) => void; onClose: () => void }) {
  return <section className={`history-layout ${detail ? "history-open" : ""}`}><div className="panel history-panel"><div className="panel-heading"><div><span className="eyebrow">YOUR ACTIVITY</span><h2>Recent conversations</h2></div><span className="history-count">{history.length} conversations</span></div>{history.length ? <div className="history-list">{history.map((item) => <button className={`history-row ${detail?.conversation_id === item.conversation_id ? "history-selected" : ""}`} key={item.conversation_id} onClick={() => onOpen(item)}><span className="history-icon"><MessageCircle size={17} /></span><span className="history-copy"><strong>{item.title || "New conversation"}</strong><small>{item.message_count} messages · Updated {formatDate(item.updated_at || item.created_at)}</small></span><ChevronRight size={17} /></button>)}</div> : <EmptyState icon={Clock3} title="Your history is clear" text="Conversations you have with AI Chat will appear here." />}</div>{detail ? <div className="panel history-detail"><div className="history-detail-head"><div><span className="eyebrow">CONVERSATION</span><h2>{detail.title}</h2></div><button className="icon-button" aria-label="Close conversation" onClick={onClose}><X size={18} /></button></div><div className="history-messages">{detail.messages.map((message) => <article className={`history-message message-${message.role}`} key={message.message_id}><span className={`message-avatar ${message.role === "assistant" ? "assistant-avatar" : "user-avatar"}`}>{message.role === "assistant" ? <Sparkles size={15} /> : "You"}</span><div className="message-body"><span className="message-byline">{message.role === "assistant" ? "NexaIQ" : "You"}<small>{formatDate(message.created_at)}</small></span><p>{message.content}</p>{message.citations ? <CitationList citations={message.citations} /> : null}</div></article>)}</div></div> : null}</section>;
}

function AdminView({ stats, health, error }: { stats: AdminStats | null; health: SystemHealth | null; error: string }) {
  if (error) return <div className="panel admin-error"><ShieldCheck size={21} /><h2>Admin data unavailable</h2><p>{error}</p><small>Admin metrics require an ADMIN or SUPER_ADMIN role and a running API.</small></div>;
  return <div className="admin-content"><section className="metric-grid"><Metric icon={Users} label="Active users" value={stats ? stats.active_users.toLocaleString() : "—"} note={stats ? `${stats.total_users} total accounts` : "Loading platform data"} tone="violet" /><Metric icon={Files} label="Documents indexed" value={stats ? stats.ready_documents.toLocaleString() : "—"} note={stats ? `${stats.total_documents} in the library` : "Loading platform data"} tone="mint" /><Metric icon={MessageCircle} label="Queries today" value={stats ? stats.queries_today.toLocaleString() : "—"} note={stats ? `${stats.total_queries} in the last year` : "Loading platform data"} tone="coral" /><Metric icon={Activity} label="Knowledge chunks" value={stats ? stats.total_chunks.toLocaleString() : "—"} note={stats ? `${stats.total_pages.toLocaleString()} pages processed` : "Loading platform data"} tone="blue" /></section><section className="panel health-panel"><div className="panel-heading"><div><span className="eyebrow">SERVICE STATUS</span><h2>System health</h2></div><span className="health-overall"><i />{health?.status || "Checking"}</span></div><div className="health-grid">{[["Database", health?.database], ["Vector store", health?.vector_store], ["Language model", health?.llm], ["Redis", health?.redis]].map(([label, value]) => <div className="health-item" key={label}><span className="health-item-icon"><Activity size={17} /></span><span><strong>{label}</strong><small>{value || "Loading"}</small></span><i className={`health-dot ${value === "ok" || value === "configured" ? "health-good" : value === "empty" || value === "not_configured" ? "health-warn" : ""}`} /></div>)}</div></section><section className="admin-lower"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">INGESTION</span><h2>Document processing</h2></div><Files size={18} /></div><div className="admin-counts"><span><b>{stats?.ready_documents ?? "—"}</b>Ready</span><span><b>{stats?.processing_documents ?? "—"}</b>Processing</span><span><b>{stats?.failed_documents ?? "—"}</b>Failed</span></div><div className="admin-bar"><i style={{ width: `${stats?.total_documents ? Math.min(100, stats.ready_documents / stats.total_documents * 100) : 0}%` }} /></div></div><div className="panel admin-note"><span className="aside-icon"><ShieldCheck size={18} /></span><h3>Access is enforced server-side</h3><p>Document visibility, role permissions and audit events are controlled by the platform API.</p></div></section></div>;
}

function EmptyState({ icon: Icon, title, text, action }: { icon: LucideIcon; title: string; text: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><Icon size={21} /></span><h3>{title}</h3><p>{text}</p>{action}</div>;
}
