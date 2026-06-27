import { NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { RequireAuth, useAuth } from "./auth";
import { Login } from "./pages/Login";
import { Workflows } from "./pages/Workflows";
import { WorkflowDetail } from "./pages/WorkflowDetail";
import { Executions } from "./pages/Executions";
import { ExecutionDetail } from "./pages/ExecutionDetail";
import { Users } from "./pages/Users";
import { Secrets } from "./pages/Secrets";
import { Agents } from "./pages/Agents";

function Wordmark() {
  return (
    <div className="wordmark">
      <span className="moira">Moira</span><span className="flow">Flow</span>
    </div>
  );
}

function Shell() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="sidebar">
        <div>
          <Wordmark />
          <div className="faint" style={{ fontSize: 11, letterSpacing: "0.14em", marginTop: 6, textTransform: "uppercase" }}>
            Automation OS
          </div>
        </div>
        <nav className="nav">
          <NavLink to="/workflows" className={({ isActive }) => (isActive ? "active" : "")}>Workflows</NavLink>
          <NavLink to="/executions" className={({ isActive }) => (isActive ? "active" : "")}>Executions</NavLink>
          {user?.role === "admin" && <>
            <NavLink to="/agents" className={({ isActive }) => (isActive ? "active" : "")}>Agents</NavLink>
            <NavLink to="/secrets" className={({ isActive }) => (isActive ? "active" : "")}>Secrets</NavLink>
            <NavLink to="/users" className={({ isActive }) => (isActive ? "active" : "")}>Users</NavLink>
          </>}
        </nav>
        <div className="grow" />
        <div className="stack" style={{ gap: 8 }}>
          <hr className="hairline" />
          <div className="mono" style={{ fontSize: 12, color: "var(--text-dim)" }}>{user?.email}</div>
          <div className="row between">
            <span className="pill">{user?.role}</span>
            <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12 }} onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><Shell /></RequireAuth>}>
        <Route index element={<Navigate to="/workflows" replace />} />
        <Route path="/workflows" element={<Workflows />} />
        <Route path="/workflows/:id" element={<WorkflowDetail />} />
        <Route path="/executions" element={<Executions />} />
        <Route path="/executions/:id" element={<ExecutionDetail />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/secrets" element={<Secrets />} />
        <Route path="/users" element={<Users />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
