import { useEffect, useState } from "react";
import { oauthLoginUrl } from "./api";
import { useAuth } from "./AuthProvider";

const providers = [
  { id: "google" as const, label: "Continue with Google", icon: "G", className: "btn-google" },
  { id: "facebook" as const, label: "Continue with Facebook", icon: "f", className: "btn-facebook" },
  { id: "apple" as const, label: "Continue with Apple", icon: "", className: "btn-apple" },
];

export function LoginPage() {
  const { authEnabled, allowGuest, backendOk, skipAuth, setSkipAuth, enterWithoutAuth } = useAuth();
  const [busy, setBusy] = useState(false);

  const handleGuest = async () => {
    setBusy(true);
    try {
      await enterWithoutAuth();
    } finally {
      setBusy(false);
    }
  };

  const skipLogin = !authEnabled || skipAuth;

  useEffect(() => {
    if (backendOk && !authEnabled) {
      setSkipAuth(true);
      void enterWithoutAuth();
    }
  }, [authEnabled, backendOk, enterWithoutAuth, setSkipAuth]);

  const handleToggle = async (checked: boolean) => {
    if (authEnabled || !backendOk) return;
    setSkipAuth(checked);
    if (!checked) return;
    setBusy(true);
    try {
      await enterWithoutAuth();
    } finally {
      setBusy(false);
    }
  };

  if (!backendOk) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-brand">
            <div className="logo-mark">AI</div>
            <h1>Backend not running</h1>
            <p>Start the API server, then reload this page.</p>
          </div>
          <pre className="dev-command">cd backend{"\n"}python -m uvicorn api.main:app --reload --port 8000</pre>
          <button type="button" className="primary-btn enter-app-btn" onClick={() => window.location.reload()}>
            Reload page
          </button>
        </div>
      </div>
    );
  }

  if (!authEnabled && skipLogin && busy) {
    return (
      <div className="login-page">
        <div className="login-card">
          <p>Opening application...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="logo-mark">AI</div>
          <h1>Notes Creator</h1>
          <p>Turn PDFs into study notes, exam prep, and grounded Q&amp;A.</p>
        </div>

        <div className="auth-toggle-row">
          <label className="auth-toggle">
            <input
              type="checkbox"
              checked={skipLogin}
              disabled={authEnabled || busy}
              onChange={(e) => void handleToggle(e.target.checked)}
            />
            <span>Skip login and open app directly</span>
          </label>
          <p className="auth-toggle-hint">
            {authEnabled
              ? "Set AUTH_ENABLED=false in .env and restart the backend to enable this."
              : "Authentication is off — opening the app without Google, Apple, or Facebook."}
          </p>
        </div>

        {authEnabled && !skipLogin && (
          <>
            <div className="login-actions">
              {providers.map((p) => (
                <a key={p.id} href={oauthLoginUrl(p.id)} className={`oauth-btn ${p.className}`}>
                  <span className="oauth-icon">{p.icon || ""}</span>
                  {p.label}
                </a>
              ))}
            </div>
            <p className="login-footnote">Sign in to save chat history and download Word files.</p>
            {allowGuest && (
              <button
                type="button"
                className="primary-btn enter-app-btn guest-btn"
                disabled={busy}
                onClick={() => void handleGuest()}
              >
                {busy ? "Loading..." : "Continue as guest"}
              </button>
            )}
          </>
        )}

        {!authEnabled && skipLogin && (
          <button
            type="button"
            className="primary-btn enter-app-btn"
            disabled={busy}
            onClick={() => void handleToggle(true)}
          >
            {busy ? "Loading..." : "Enter application"}
          </button>
        )}
      </div>
    </div>
  );
}
