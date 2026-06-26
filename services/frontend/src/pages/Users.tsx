import { useEffect, useState } from "react";
import { api, ApiError, type Role, type User } from "../api";

const ROLES: Role[] = ["admin", "operator", "developer", "viewer"];

export function Users() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.listUsers().then(setUsers).catch(() => setUsers([]));
  useEffect(() => { load(); }, []);

  const create = async () => {
    setErr(null);
    try {
      await api.createUser(email, password, role);
      setEmail(""); setPassword(""); load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "failed");
    }
  };

  return (
    <div>
      <div className="page-head">
        <div><div className="eyebrow">Governance</div><h1 className="page-title">Users</h1></div>
      </div>

      <div className="panel" style={{ padding: 18, marginBottom: 20 }}>
        <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div className="grow"><label className="label">Email</label>
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@org.io" /></div>
          <div><label className="label">Password</label>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          <div><label className="label">Role</label>
            <select className="select" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => <option key={r}>{r}</option>)}
            </select></div>
          <button className="btn btn-gold" onClick={create} disabled={!email || !password}>Add user</button>
        </div>
        {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
      </div>

      <div className="panel" style={{ overflow: "hidden" }}>
        {users === null ? <div className="empty">Loading…</div> : (
          <table className="table">
            <thead><tr><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="mono">{u.email}</td>
                  <td><span className="pill">{u.role}</span></td>
                  <td className={u.is_active ? "" : "faint"}>{u.is_active ? "active" : "inactive"}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12 }}
                      onClick={() => api.setUserActive(u.id, !u.is_active).then(load)}>
                      {u.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
