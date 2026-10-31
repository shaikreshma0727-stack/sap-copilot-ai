import { useEffect, useRef, useState } from "react";
import { getHistory, login, pingServer, register, sendMessage } from "./api.js";
import CodeReview from "./CodeReview.jsx";
import ErrorAnalyzer from "./ErrorAnalyzer.jsx";
import SpecGenerator from "./SpecGenerator.jsx";
import InterviewCoach from "./InterviewCoach.jsx";
import Markdown from "./Markdown.jsx";

const AGENT_LABELS = {
  abap: "ABAP Agent",
  functional: "Functional Agent",
  learning: "Learning Agent",
};

// Free hosting sleeps when idle. Shows a notice while the first request wakes the server up.
function ServerStatus() {
  const [state, setState] = useState("checking");
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => alive && setSlow(true), 2500);
    pingServer().then((ok) => {
      if (alive) setState(ok ? "up" : "down");
    });
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  if (state === "up") return null;
  if (state === "down") {
    return <div className="notice warn">The server could not be reached. Please try again in a minute.</div>;
  }
  return slow ? (
    <div className="notice">The free demo server was asleep and is starting now. This can take up to a minute.</div>
  ) : null;
}

function AuthForm({ onLoggedIn }) {
  const [mode, setMode] = useState("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") await register(email, password, fullName);
      const { access_token } = await login(email, password);
      onLoggedIn(access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card auth" onSubmit={submit}>
      <h1>SAP Copilot AI</h1>
      <p className="muted">Your AI assistant for the SAP project lifecycle</p>
      {mode === "register" && (
        <input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      )}
      <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      <input
        type="password"
        placeholder="Password (min 8 characters)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        minLength={8}
        required
      />
      <ServerStatus />
      <p className="fineprint">
        Demo: chats and answers are stored on the server. Please do not enter confidential or client data. AI use is limited.
      </p>
      {error && <div className="error">{error}</div>}
      <button type="submit" disabled={busy}>
        {busy ? "Please wait..." : mode === "login" ? "Log in" : "Create account"}
      </button>
      <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "New here? Create an account" : "Already have an account? Log in"}
      </button>
    </form>
  );
}

function Chat({ token, onLogout, onNavigate }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    getHistory(token)
      .then((items) => {
        const ordered = [...items].reverse();
        setMessages(
          ordered.flatMap((m) => [
            { role: "user", text: m.question },
            { role: "assistant", text: m.answer, agent: m.agent },
          ])
        );
      })
      .catch((err) => {
        if (err.message.includes("token")) onLogout();
      });
  }, [token]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setError("");
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await sendMessage(text, token);
      setMessages((m) => [...m, { role: "assistant", text: res.answer, agent: res.agent }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <header>
        <strong>SAP Copilot AI</strong>
        <span className="nav">
          <button className="link active">Chat</button>
          <button className="link" onClick={() => onNavigate("coach")}>Interview coach</button>
          <button className="link" onClick={() => onNavigate("errors")}>Error analyzer</button>
          <button className="link" onClick={() => onNavigate("spec")}>FS to TS</button>
          <button className="link" onClick={() => onNavigate("review")}>Code review</button>
          <button className="link" onClick={onLogout}>Log out</button>
        </span>
      </header>
      <div className="messages">
        {messages.length === 0 && (
          <p className="muted center">
            Try: "Create a Purchase Requisition upload program" or "Explain the procure-to-pay process"
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.agent && <div className="agent">{AGENT_LABELS[m.agent] || m.agent}</div>}
            {m.role === "assistant" ? <Markdown>{m.text}</Markdown> : <pre>{m.text}</pre>}
          </div>
        ))}
        {busy && <div className="bubble assistant muted">Thinking...</div>}
        {error && <div className="error">{error}</div>}
        <div ref={bottomRef} />
      </div>
      <form className="composer" onSubmit={send}>
        <input
          placeholder="Ask anything about SAP..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" disabled={busy}>Send</button>
      </form>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("token"));
  const [view, setView] = useState("chat");

  function handleLogin(t) {
    sessionStorage.setItem("token", t);
    setToken(t);
  }
  function handleLogout() {
    sessionStorage.removeItem("token");
    setToken(null);
  }

  if (!token) return <AuthForm onLoggedIn={handleLogin} />;
  if (view === "coach") return <InterviewCoach token={token} onLogout={handleLogout} onNavigate={setView} />;
  if (view === "errors") return <ErrorAnalyzer token={token} onLogout={handleLogout} onNavigate={setView} />;
  if (view === "spec") return <SpecGenerator token={token} onLogout={handleLogout} onNavigate={setView} />;
  if (view === "review") return <CodeReview token={token} onLogout={handleLogout} onNavigate={setView} />;
  return <Chat token={token} onLogout={handleLogout} onNavigate={setView} />;
}
