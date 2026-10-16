import PasswordInput from "./PasswordInput";
import React, { useEffect, useState } from "react";
import { api, setSession } from "../api";

export default function AuthGate({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [changing, setChanging] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    document.documentElement.dataset.theme = localStorage.getItem("labelling-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    api("/auth/me").then((value) => { setSession(value); setUser(value); })
      .catch((error) => { if (!error.message.includes("Sign in") && !error.message.includes("expired")) setError(error.message); })
      .finally(() => setLoading(false));
    const expired = () => { setUser(null); setSession(null); setNotice("Your session ended. Sign in again."); };
    window.addEventListener("studio-session-ended", expired);
    return () => window.removeEventListener("studio-session-ended", expired);
  }, []);
  async function logout() {
    try { await api("/auth/logout", { method: "POST" }); }
    catch (error) { setError(error.message); return; }
    setUser(null); setSession(null); setChanging(false);
    sessionStorage.removeItem("studio-open-project");
  }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (changing || user?.must_change_password) {
        if (values.password !== values.confirm_password) throw new Error("The new passwords do not match.");
        delete values.confirm_password;
        await api("/auth/password", { method: "POST", body: JSON.stringify(values) });
        setUser(null); setSession(null); setChanging(false); setNotice("Password changed. Sign in with your new password.");
      } else {
        const value = await api("/auth/login", { method: "POST", body: JSON.stringify(values) });
        setSession(value); setUser(value);
      }
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }
  if (loading) return <main className="auth-page"><p role="status">Connecting to AI Studio…</p></main>;
  if (user && !user.must_change_password && !changing) return children(user, logout, () => setChanging(true));
  const passwordChange = changing || user?.must_change_password;
  return <main className="auth-page"><form className="panel auth-card" onSubmit={submit} key={String(passwordChange)}>
    <img width="44" height="44" src="/favicon.svg" alt="" />
    <div><div className="eyebrow">AI STUDIO</div><h1>{passwordChange ? "Choose a new password" : "Sign in"}</h1>
      <p className="muted">{passwordChange ? "Use at least 12 characters. Changing your password signs out existing sessions." : "Access the dataset repositories shared with you."}</p></div>
    {!passwordChange && <label>Username<input name="username" required maxLength="80" pattern="[a-zA-Z0-9_.\-]+" autoComplete="username" autoFocus /></label>}
    {passwordChange && <label>Current password<PasswordInput name="current_password" required autoComplete="current-password" /></label>}
    <label>{passwordChange ? "New password" : "Password"}<PasswordInput name="password" required minLength={passwordChange ? 12 : 1} maxLength="1024" autoComplete={passwordChange ? "new-password" : "current-password"} /></label>
    {passwordChange && <label>Confirm new password<PasswordInput name="confirm_password" required minLength="12" autoComplete="new-password" /></label>}
    {error && <p className="alert" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
    <div className="actions"><button className="primary" disabled={busy}>{busy ? "Please wait…" : passwordChange ? "Change password" : "Sign in"}</button>
      {changing && !user?.must_change_password && <button type="button" onClick={() => setChanging(false)}>Cancel</button>}
      {user?.must_change_password && <button type="button" onClick={logout}>Sign out</button>}</div>
  </form></main>;
}
