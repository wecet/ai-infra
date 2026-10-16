import React, { useEffect, useState } from "react";

export default function PasswordInput({ revealLabel, ...props }) {
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    const hide = () => setRevealed(false);
    const visibility = () => { if (document.hidden) hide(); };
    window.addEventListener("pointerup", hide);
    window.addEventListener("pointercancel", hide);
    window.addEventListener("keyup", hide);
    window.addEventListener("blur", hide);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.removeEventListener("pointerup", hide);
      window.removeEventListener("pointercancel", hide);
      window.removeEventListener("keyup", hide);
      window.removeEventListener("blur", hide);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  const label = revealLabel || props.name?.replaceAll("_", " ") || "password";
  return <span className="password-input">
    <input {...props} type={revealed ? "text" : "password"} />
    <button type="button" className="password-reveal" disabled={props.disabled}
      aria-label={`Hold to reveal ${label}`} aria-pressed={revealed} title="Hold to reveal password"
      onPointerDown={(event) => { if (event.button === 0) setRevealed(true); }}
      onPointerUp={() => setRevealed(false)} onPointerCancel={() => setRevealed(false)}
      onPointerLeave={() => setRevealed(false)} onBlur={() => setRevealed(false)}
      onKeyDown={(event) => {
        if (event.key === " " || event.key === "Enter") { event.preventDefault(); setRevealed(true); }
        if (event.key === "Escape") setRevealed(false);
      }} onKeyUp={() => setRevealed(false)}
      onContextMenu={(event) => event.preventDefault()}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true" focusable="false">
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
        {revealed && <path d="m4 3 16 18" />}
      </svg>
    </button>
  </span>;
}
