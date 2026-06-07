import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ChatApp } from "./App";
import { AuthProvider, useAuth } from "../auth/AuthProvider";
import { LoginPage } from "../auth/LoginPage";
import { AuthCallbackPage } from "../auth/AuthCallbackPage";
import "./styles.css";

function Root() {
  const path = window.location.pathname;
  if (path === "/auth/callback") {
    return (
      <AuthProvider>
        <AuthCallbackPage />
      </AuthProvider>
    );
  }

  return (
    <AuthProvider>
      <AppRouter />
    </AuthProvider>
  );
}

function AppRouter() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="login-page">
        <div className="login-card"><p>Loading...</p></div>
      </div>
    );
  }
  if (!user) return <LoginPage />;
  return <ChatApp />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>
);
