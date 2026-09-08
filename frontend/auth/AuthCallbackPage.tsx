import { useEffect } from "react";
import { useAuth } from "./AuthProvider";

export function AuthCallbackPage() {
  const { loginWithToken } = useAuth();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      loginWithToken(token).then(() => {
        window.history.replaceState({}, "", "/");
      });
    }
  }, [loginWithToken]);

  return (
    <div className="login-page">
      <div className="login-card">
        <p>Signing you in...</p>
      </div>
    </div>
  );
}
