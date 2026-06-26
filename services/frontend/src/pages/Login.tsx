import { motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";

export function Login() {
  const { login, user } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@moiraflow.local");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) { nav("/", { replace: true }); }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      await login(email, password);
      nav("/", { replace: true });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Login failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="login-wrap">
      <motion.div
        className="panel login-card"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="wordmark" style={{ fontSize: 28 }}>
          <span className="moira">Moira</span><span className="flow">Flow</span>
        </div>
        <p className="dim" style={{ fontSize: 13.5, marginTop: 10, marginBottom: 26, lineHeight: 1.5 }}>
          The Fates wove the thread of destiny.<br />MoiraFlow weaves the threads of your workflows.
        </p>
        <form onSubmit={submit}>
          <div className="field">
            <label className="label">Email</label>
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          </div>
          <div className="field">
            <label className="label">Password</label>
            <input className="input" type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          {err && <div className="err" style={{ marginBottom: 14 }}>{err}</div>}
          <button className="btn btn-gold" style={{ width: "100%", padding: 11 }} disabled={busy}>
            {busy ? "Spinning the thread…" : "Enter"}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
