import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, token, type User } from "./api";

interface AuthCtx {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!token.get()) { setReady(true); return; }
    api.me().then(setUser).catch(() => token.clear()).finally(() => setReady(true));
  }, []);

  const login = async (email: string, password: string) => {
    const { access_token } = await api.login(email, password);
    token.set(access_token);
    setUser(await api.me());
  };
  const logout = () => { token.clear(); setUser(null); };

  return <Ctx.Provider value={{ user, ready, login, logout }}>{children}</Ctx.Provider>;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return null;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <>{children}</>;
}

export function canWrite(role?: string) {
  return role === "admin" || role === "developer";
}
export function canLaunch(role?: string) {
  return role === "admin" || role === "developer" || role === "operator";
}
