"use client";

import {
  Activity, ArrowLeft, CheckCircle2, Download, FileText, Files, LoaderCircle, LogOut,
  RefreshCw, ShieldCheck, Trash2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, clearSession, downloadApiFile, saveSession, type AdminDocument, type AdminStats, type AdminUser, type AuditLogRecord, type CurrentUser, type SystemHealth } from "@/lib/api";
import { AppearanceMenu, ThemeToggle } from "@/components/theme-provider";

type AccessState = "checking" | "admin-gate" | "allowed" | "signed-out" | "denied" | "error";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatBytes(value: number) {
  return value < 1024 * 1024 ? `${Math.max(1, Math.round(value / 1024))} KB` : `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined) return "N/A";
  if (value < 60) return `${Math.floor(value)} sec`;
  return `${Math.floor(value / 60)} min ${Math.floor(value % 60)} sec`;
}

export default function AdminPage() {
  const router = useRouter();
  const [access, setAccess] = useState<AccessState>("checking");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [documents, setDocuments] = useState<AdminDocument[]>([]);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [roleDrafts, setRoleDrafts] = useState<Record<string, string>>({});
  const [busyDocument, setBusyDocument] = useState<string | null>(null);
  const [busyUser, setBusyUser] = useState<string | null>(null);
  const [reindexBusy, setReindexBusy] = useState(false);
  const [auditBusy, setAuditBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [gateBusy, setGateBusy] = useState(false);
  const [gateError, setGateError] = useState("");

  async function loadAdminData() {
    const [dashboard, system, docs, userList, auditList] = await Promise.all([
      api<AdminStats>("/api/v1/admin/dashboard"),
      api<SystemHealth>("/api/v1/admin/health"),
      api<{ documents: AdminDocument[]; total: number }>("/api/v1/admin/documents?page=1&page_size=50"),
      api<{ users: AdminUser[]; total: number }>("/api/v1/users?page=1&page_size=100"),
      api<{ logs: AuditLogRecord[]; total: number }>("/api/v1/admin/audit-logs?page=1&page_size=25"),
    ]);
    setStats(dashboard);
    setHealth(system);
    setDocuments(docs.documents);
    setTotalDocuments(docs.total);
    setUsers(userList.users);
    setAuditLogs(auditList.logs);
  }

  useEffect(() => {
    let active = true;
    async function verifyAccess() {
      if (!sessionStorage.getItem("access_token")) {
        setAccess("signed-out");
        return;
      }
      try {
        const profile = await api<CurrentUser>("/api/v1/auth/me");
        if (!active) return;
        if (!["ADMIN", "SUPER_ADMIN"].includes(profile.role.toUpperCase())) {
          setAccess("denied");
          return;
        }
        setUser(profile);
        setAdminEmail(profile.email);
        if (active) setAccess("admin-gate");
      } catch (requestError) {
        if (!active) return;
        const message = requestError instanceof Error ? requestError.message : "Admin data could not be loaded.";
        if (message.toLowerCase().includes("permission") || message.toLowerCase().includes("administrator")) {
          setAccess("denied");
        } else if (message.toLowerCase().includes("session has expired")) {
          clearSession();
          setAccess("signed-out");
        } else {
          setError(message);
          setAccess("error");
        }
      }
    }
    void verifyAccess();
    return () => { active = false; };
  }, []);

  async function confirmAdminAccess(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (gateBusy) return;
    setGateBusy(true);
    setGateError("");
    const previousRefreshToken = sessionStorage.getItem("refresh_token");
    const previousUserId = user?.user_id;
    try {
      const tokens = await api<{ access_token: string; refresh_token: string }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: adminEmail, password: adminPassword }),
      });
      saveSession(tokens.access_token, tokens.refresh_token);
      const verified = await api<CurrentUser>("/api/v1/auth/me");
      if (!["ADMIN", "SUPER_ADMIN"].includes(verified.role.toUpperCase())) {
        await api("/api/v1/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: tokens.refresh_token }) }).catch(() => undefined);
        clearSession();
        setAccess("denied");
        return;
      }
      if (previousRefreshToken && previousUserId === verified.user_id) {
        await api("/api/v1/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: previousRefreshToken }) }).catch(() => undefined);
      }
      setUser(verified);
      setAdminPassword("");
      await loadAdminData();
      setAccess("allowed");
    } catch (requestError) {
      setGateError(requestError instanceof Error ? requestError.message : "Administrator verification failed.");
    } finally {
      setGateBusy(false);
    }
  }

  useEffect(() => {
    const processing = documents.some((document) => ["uploaded", "processing", "pending"].includes(document.status.toLowerCase()));
    if (access !== "allowed" || !processing) return;
    let active = true;
    const timer = window.setInterval(() => {
      void Promise.all([
        api<AdminStats>("/api/v1/admin/dashboard"),
        api<{ documents: AdminDocument[]; total: number }>("/api/v1/admin/documents?page=1&page_size=50"),
      ]).then(([nextStats, nextDocuments]) => {
        if (!active) return;
        setStats(nextStats);
        setDocuments(nextDocuments.documents);
        setTotalDocuments(nextDocuments.total);
      }).catch((requestError) => {
        if (!active) return;
        const message = requestError instanceof Error ? requestError.message : "Could not refresh ingestion status.";
        if (message.toLowerCase().includes("permission")) setAccess("denied");
        else setError(message);
      });
    }, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, [access, documents]);

  async function refreshData() {
    setError("");
    try { await loadAdminData(); }
    catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Could not refresh admin data.";
      if (message.toLowerCase().includes("permission")) setAccess("denied");
      else setError(message);
    }
  }

  async function reindexDocument(document: AdminDocument) {
    setBusyDocument(document.document_id); setNotice(""); setError("");
    try {
      await api(`/api/v1/documents/${document.document_id}/reindex`, { method: "POST" });
      setNotice(`Reindexing started for ${document.filename}.`);
      await refreshData();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not reindex the document."); }
    finally { setBusyDocument(null); }
  }

  async function deleteDocument(document: AdminDocument) {
    if (!window.confirm(`Delete ${document.filename}? This removes it from the knowledge base.`)) return;
    setBusyDocument(document.document_id); setNotice(""); setError("");
    try {
      await api(`/api/v1/documents/${document.document_id}`, { method: "DELETE" });
      setNotice(`${document.filename} was removed from the knowledge base.`);
      await refreshData();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not delete the document."); }
    finally { setBusyDocument(null); }
  }

  async function reindexAll() {
    setReindexBusy(true); setNotice(""); setError("");
    try {
      const result = await api<{ status: string; documents_queued: number; skipped_in_progress: number }>("/api/v1/admin/vector/reindex", { method: "POST" });
      setNotice(`Vector re-index ${result.status}. ${result.documents_queued} documents queued; ${result.skipped_in_progress} already in progress.`);
      await refreshData();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not start vector re-indexing."); }
    finally { setReindexBusy(false); }
  }

  async function exportAuditLog() {
    setAuditBusy(true); setError("");
    try {
      await downloadApiFile("/api/v1/admin/audit-logs/export", "enterprise-audit-log.csv");
      setNotice("Audit log exported.");
      const result = await api<{ logs: AuditLogRecord[]; total: number }>("/api/v1/admin/audit-logs?page=1&page_size=25");
      setAuditLogs(result.logs);
    }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not export the audit log."); }
    finally { setAuditBusy(false); }
  }

  async function changeUserRole(target: AdminUser) {
    const role = roleDrafts[target.user_id] || target.role;
    if (role === target.role) return;
    setBusyUser(target.user_id); setError(""); setNotice("");
    try {
      const updated = await api<AdminUser>(`/api/v1/users/${target.user_id}/role`, { method: "PATCH", body: JSON.stringify({ role }) });
      setUsers((current) => current.map((item) => item.user_id === updated.user_id ? updated : item));
      setNotice(`Role updated for ${updated.name}.`);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not update the user role."); }
    finally { setBusyUser(null); }
  }

  async function setUserActive(target: AdminUser) {
    if (target.user_id === user?.user_id) return;
    const nextActive = !target.is_active;
    if (!nextActive && !window.confirm(`Deactivate ${target.name}? Their active sessions will be revoked.`)) return;
    setBusyUser(target.user_id); setError(""); setNotice("");
    try {
      const updated = nextActive
        ? await api<AdminUser>(`/api/v1/users/${target.user_id}`, { method: "PATCH", body: JSON.stringify({ is_active: true }) })
        : null;
      if (!nextActive) await api(`/api/v1/users/${target.user_id}`, { method: "DELETE" });
      const result = updated || { ...target, is_active: false };
      setUsers((current) => current.map((item) => item.user_id === result.user_id ? result : item));
      setNotice(`${result.name} ${result.is_active ? "activated" : "deactivated"}.`);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not update user status."); }
    finally { setBusyUser(null); }
  }

  async function signOut() {
    const refreshToken = sessionStorage.getItem("refresh_token");
    if (refreshToken) {
      try { await api("/api/v1/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) }); } catch { /* Clear local session even if the API is unavailable. */ }
    }
    clearSession();
    router.replace("/");
  }

  if (access === "checking") return <main className="boot-screen"><LoaderCircle className="spin" size={20} /></main>;
  if (access === "signed-out") return <AccessMessage title="Sign in required" detail="Sign in to your workspace before requesting administrator access." action={<button className="button button-primary" onClick={() => router.replace("/")}>Go to sign in<ArrowLeft size={15} /></button>} />;
  if (access === "denied") return <AccessMessage title="403 · Access denied" detail="You do not have permission to access the administrator workspace." action={<button className="button button-primary" data-testid="admin-return-dashboard" onClick={() => router.replace("/")}>Return to dashboard<ArrowLeft size={15} /></button>} />;
  if (access === "admin-gate") return <AdminAccessGate email={adminEmail} password={adminPassword} setEmail={setAdminEmail} setPassword={setAdminPassword} busy={gateBusy} error={gateError} onSubmit={confirmAdminAccess} onBack={() => router.push("/")} />;

  return <div className="workspace admin-workspace">
    <aside className="sidebar">
      <div className="sidebar-head"><Link className="brand" href="/"><span className="brand-mark"><ShieldCheck size={17} /></span><span>NexaIQ</span></Link></div>
      <div className="workspace-switch"><span className="workspace-avatar">A</span><span className="workspace-label"><strong>Administration</strong><small>Restricted workspace</small></span></div>
      <span className="nav-caption">ADMINISTRATION</span>
      <nav className="main-nav" aria-label="Admin navigation"><button className="nav-link nav-active"><Activity size={18} /><span>Admin dashboard</span></button></nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-bottom"><span className="engine-dot" /><span>Administrator access</span></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="topbar-left"><button className="button button-secondary" onClick={() => router.push("/")}><ArrowLeft size={15} />Back to workspace</button></div><div className="topbar-right"><span className={`backend-indicator ${health?.status !== "ok" ? "offline" : ""}`}><span />Backend {health?.status === "ok" ? "connected" : "degraded"}</span><AppearanceMenu className="icon-button theme-toggle" /><button className="profile-button" onClick={signOut} title="Sign out"><span className="avatar">{user?.name.slice(0, 1).toUpperCase() || "A"}</span><span className="profile-copy"><strong>{user?.name}</strong><small>{user?.role}</small></span><LogOut size={15} /></button></div></header>
      <div className="content-wrap">
        <div className="page-heading"><div><span className="eyebrow">RESTRICTED WORKSPACE</span><h1>Admin Dashboard</h1><p>Knowledge base operations and system health.</p></div><div className="admin-header-actions"><button className="button button-secondary" data-testid="vector-reindex-button" disabled={reindexBusy} onClick={() => { void reindexAll(); }}>{reindexBusy ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}{reindexBusy ? "Re-indexing" : "Trigger Vector Re-index"}</button><button className="button button-secondary" data-testid="audit-log-export-button" disabled={auditBusy} onClick={() => { void exportAuditLog(); }}>{auditBusy ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}{auditBusy ? "Exporting" : "Export Audit Log"}</button><button className="button button-secondary" data-testid="admin-refresh-button" onClick={() => { void refreshData(); }}><RefreshCw size={15} />Refresh</button></div></div>
        {error ? <div className="notice notice-error" role="alert"><span>{error}</span></div> : null}
        {notice ? <div className="notice notice-success" role="status"><span><CheckCircle2 size={16} />{notice}</span></div> : null}
        <section className="metric-grid admin-kpis" aria-label="Knowledge base metrics">
          <Metric label="Total documents" value={stats?.total_documents ?? "—"} detail="In the knowledge base" tone="violet" />
          <Metric label="Ready to query" value={stats?.ready_documents ?? "—"} detail={`${stats?.searchable_documents ?? 0} searchable`} tone="mint" />
          <Metric label="Processing" value={stats?.processing_documents ?? "—"} detail="Indexing in progress" tone="blue" />
          <Metric label="Failed" value={stats?.failed_documents ?? "—"} detail="Needs review" tone="coral" />
        </section>
        <section className="panel health-panel"><div className="panel-heading"><div><span className="eyebrow">SERVICE STATUS</span><h2>System health</h2></div><span className="health-overall"><i />{health?.status || "checking"}</span></div><div className="health-grid">
          {[ ["Backend", health?.status], ["Database", health?.database], ["Vector store", health?.vector_store], ["Embeddings", health?.embeddings], ["LLM", health?.llm], ["Redis", health?.redis], ["Workers", health?.worker_count == null ? "N/A" : String(health.worker_count)], ["Uptime", formatDuration(health?.uptime_seconds)] ].map(([label, value]) => <div className="health-item" key={label}><span className="health-item-icon"><Activity size={17} /></span><span><strong>{label}</strong><small>{value || "Loading"}</small></span><i className={`health-dot ${value === "ok" || value === "ready" || value === "configured" ? "health-good" : value === "not_configured" || value === "empty" || value === "not_loaded" || value === "N/A" ? "health-warn" : ""}`} /></div>)}
        </div></section>
        <section className="admin-knowledge-grid"><div className="panel health-panel"><div className="panel-heading"><div><span className="eyebrow">KNOWLEDGE BASE</span><h2>Index summary</h2></div><Files size={18} /></div><div className="admin-counts"><span><b>{stats?.total_pages.toLocaleString() ?? "—"}</b>Pages</span><span><b>{stats?.total_chunks.toLocaleString() ?? "—"}</b>Chunks</span><span><b>{stats?.searchable_documents.toLocaleString() ?? "—"}</b>Searchable</span></div></div><div className="panel health-panel"><div className="panel-heading"><div><span className="eyebrow">RAG DIAGNOSTICS</span><h2>Recent query performance</h2></div><Activity size={18} /></div><div className="admin-counts"><span><b>{stats?.average_retrieval_ms == null ? "N/A" : `${stats.average_retrieval_ms} ms`}</b>Average hybrid retrieval</span><span><b>{stats?.average_llm_ms == null ? "N/A" : `${stats.average_llm_ms} ms`}</b>Average LLM</span><span><b>{stats?.average_total_ms == null ? "N/A" : `${stats.average_total_ms} ms`}</b>Average total</span></div><div className="admin-diagnostic-note">Candidates {stats?.retrieval_top_k ?? "N/A"} · Final context {stats?.rerank_top_k ?? "N/A"} · Separate vector/embedding latency: N/A</div></div><div className="panel admin-note"><span className="aside-icon"><ShieldCheck size={18} /></span><h3>Access is enforced by FastAPI</h3><p>Admin APIs independently validate the authenticated role. Document-level access rules remain active for normal users.</p></div></section>
        <section className="panel documents-panel admin-documents-panel"><div className="panel-heading admin-documents-heading"><div><span className="eyebrow">INGESTION MONITORING</span><h2>Document management</h2></div><span className="history-count">{totalDocuments} documents</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>DOCUMENT</th><th>OWNER</th><th>PAGES / CHUNKS</th><th>STATUS</th><th>UPLOADED</th><th>ACTIONS</th></tr></thead><tbody>{documents.map((document) => <tr key={document.document_id}><td><div className="file-cell"><span className="file-icon"><FileText size={17} /></span><span><strong>{document.filename}</strong><small>{formatBytes(document.file_size)}</small>{document.error_message ? <small className="inline-error">{document.error_message}</small> : null}</span></div></td><td><span className="admin-owner">{document.owner_name}</span><small className="admin-owner-email">{document.owner_email}</small></td><td>{document.page_count ?? "—"} / {document.chunk_count ?? "—"}</td><td><span className={`status-pill status-${document.status.toLowerCase()}`}>{document.status}</span></td><td>{formatDate(document.created_at)}</td><td><div className="admin-actions">{document.status.toLowerCase() === "failed" ? <button className="icon-button row-action" data-testid="document-reindex-button" aria-label={`Retry indexing ${document.filename}`} disabled={busyDocument === document.document_id} onClick={() => { void reindexDocument(document); }}><RefreshCw size={15} /></button> : null}<button className="icon-button row-action admin-delete-action" data-testid="admin-delete-document-button" aria-label={`Delete ${document.filename}`} disabled={busyDocument === document.document_id} onClick={() => { void deleteDocument(document); }}><Trash2 size={15} /></button></div></td></tr>)}</tbody></table>{documents.length === 0 ? <div className="empty-inline">No documents found.</div> : null}</div></section>
        <section className="panel documents-panel admin-users-panel"><div className="panel-heading admin-documents-heading"><div><span className="eyebrow">ACCESS MANAGEMENT</span><h2>Active users & permissions</h2></div><span className="history-count">{users.filter((item) => item.is_active).length} active · {users.length} listed</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>USER</th><th>EMAIL</th><th>ROLE</th><th>DOCUMENT ACCESS SCOPE</th><th>LAST ACTIVE</th><th>ACTIONS</th></tr></thead><tbody>{users.map((target) => { const isSelf = target.user_id === user?.user_id; const canChangeRole = user?.role === "SUPER_ADMIN" && !isSelf; const canDeactivate = !isSelf && (user?.role === "SUPER_ADMIN" || (user?.role === "ADMIN" && !["ADMIN", "SUPER_ADMIN"].includes(target.role))); const selectedRole = roleDrafts[target.user_id] || target.role; return <tr key={target.user_id}><td><span className="admin-owner">{target.name}</span><small className="admin-owner-email">{target.is_active ? "Active" : "Disabled"}</small></td><td>{target.email}</td><td><span className={`status-pill ${target.role === "ADMIN" || target.role === "SUPER_ADMIN" ? "status-ready" : "status-uploaded"}`}>{target.role}</span></td><td>{target.department ? `Department: ${target.department}` : "Owner and role grants"}</td><td>{target.last_login ? formatDate(target.last_login) : "Never"}</td><td><div className="admin-actions">{canChangeRole ? <><select className="admin-role-select" aria-label={`Role for ${target.name}`} value={selectedRole} disabled={busyUser === target.user_id} onChange={(event) => setRoleDrafts((current) => ({ ...current, [target.user_id]: event.target.value }))}>{["ADMIN", "EMPLOYEE", "STUDENT", "SUPER_ADMIN"].map((role) => <option key={role} value={role}>{role}</option>)}</select><button className="button button-secondary admin-save-role" disabled={busyUser === target.user_id || selectedRole === target.role} onClick={() => { void changeUserRole(target); }}>Save</button></> : null}{canDeactivate ? <button className="icon-button row-action admin-delete-action" aria-label={`${target.is_active ? "Disable" : "Enable"} ${target.name}`} disabled={busyUser === target.user_id} onClick={() => { void setUserActive(target); }}><Trash2 size={15} /></button> : null}</div></td></tr>; })}</tbody></table></div></section>
        <section className="panel documents-panel admin-audit-panel"><div className="panel-heading admin-documents-heading"><div><span className="eyebrow">SECURITY & GOVERNANCE</span><h2>Recent audit activity</h2></div><span className="history-count">Latest {auditLogs.length}</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>TIME</th><th>ADMIN / USER</th><th>ACTION</th><th>RESOURCE</th><th>RESULT DETAILS</th></tr></thead><tbody>{auditLogs.map((log) => <tr key={log.log_id}><td>{formatDate(log.timestamp)}</td><td>{log.user_id || "System"}</td><td><span className="classification">{log.action}</span></td><td>{[log.resource_type, log.resource_id].filter(Boolean).join(" · ") || "—"}</td><td>{log.metadata ? JSON.stringify(log.metadata) : "—"}</td></tr>)}</tbody></table>{auditLogs.length === 0 ? <div className="empty-inline">No audit activity yet.</div> : null}</div></section>
        <footer className="page-footer"><span>NEXAIQ · ADMINISTRATION</span><span>All displayed values are read from protected backend APIs.</span></footer>
      </div>
    </main>
  </div>;
}

function Metric({ label, value, detail, tone }: { label: string; value: number | string; detail: string; tone: string }) {
  return <article className="metric-card"><span className={`metric-icon metric-${tone}`}><FileText size={18} /></span><span className="metric-label">{label}</span><strong className="metric-value">{typeof value === "number" ? value.toLocaleString() : value}</strong><span className="metric-note">{detail}</span></article>;
}

function AccessMessage({ title, detail, action }: { title: string; detail: string; action: React.ReactNode }) {
  return <main className="auth-screen"><section className="panel admin-access-message"><span className="empty-icon"><ShieldCheck size={22} /></span><span className="eyebrow">RESTRICTED WORKSPACE</span><h1>{title}</h1><p>{detail}</p>{action}</section></main>;
}

function AdminAccessGate({ email, password, setEmail, setPassword, busy, error, onSubmit, onBack }: {
  email: string;
  password: string;
  setEmail: (value: string) => void;
  setPassword: (value: string) => void;
  busy: boolean;
  error: string;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onBack: () => void;
}) {
  return <main className="auth-screen">
    <div className="auth-art" aria-hidden="true"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-core"><ShieldCheck size={23} /></div><div className="art-caption"><span className="eyebrow">RESTRICTED WORKSPACE</span><p>Administrator<br />access.</p></div></div>
    <section className="auth-panel"><Link className="brand auth-brand" href="/"><span className="brand-mark"><ShieldCheck size={18} /></span><span>NexaIQ</span></Link><ThemeToggle className="icon-button auth-theme-toggle" /><div className="auth-form-wrap"><span className="eyebrow">ADMINISTRATOR ACCESS</span><h1>Restricted workspace</h1><p className="muted">Re-enter your administrator credentials to continue to the administration console.</p>
      <form className="auth-form" data-testid="admin-login-form" onSubmit={onSubmit}><label>Email<input autoComplete="username" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="admin@company.com" /></label><label>Password<input autoComplete="current-password" type="password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Administrator password" /></label>{error ? <p className="form-message error-message" role="alert">{error}</p> : null}<button className="button button-primary auth-submit" data-testid="admin-login-submit" disabled={busy} type="submit">{busy ? <LoaderCircle className="spin" size={17} /> : null}Continue to Admin Dashboard</button></form>
      <button className="admin-back-link" onClick={onBack}><ArrowLeft size={15} />Back to Workspace</button>
    </div><span className="auth-version">NEXAIQ · SECURE ADMIN ACCESS</span></section>
  </main>;
}