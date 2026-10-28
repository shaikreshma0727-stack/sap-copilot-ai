import { useState } from "react";
import { reviewCode } from "./api.js";
import Markdown from "./Markdown.jsx";

function Finding({ f }) {
  return (
    <details className="err-match" open={f.severity === "high"}>
      <summary>
        <span className={`sev sev-${f.severity}`}>{f.severity}</span> Line {f.line}: {f.title}
      </summary>
      {f.code && <pre className="snippet">{f.code}</pre>}
      <p>
        <strong>Why:</strong> {f.why}
      </p>
      <p>
        <strong>Try:</strong> {f.suggestion}
      </p>
    </details>
  );
}

export default function CodeReview({ token, onLogout, onNavigate }) {
  const [code, setCode] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (code.trim().length < 10 || busy) return;
    setError("");
    setResult(null);
    setBusy(true);
    try {
      setResult(await reviewCode(code, token));
    } catch (err) {
      if (err.message.toLowerCase().includes("token")) onLogout();
      else setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const counts = result
    ? ["high", "medium", "low", "info"].map((s) => [s, result.findings.filter((f) => f.severity === s).length]).filter(([, n]) => n > 0)
    : [];

  return (
    <div className="chat">
      <header>
        <strong>SAP Copilot AI</strong>
        <span className="nav">
          <button className="link" onClick={() => onNavigate("chat")}>Chat</button>
          <button className="link" onClick={() => onNavigate("coach")}>Interview coach</button>
          <button className="link" onClick={() => onNavigate("errors")}>Error analyzer</button>
          <button className="link" onClick={() => onNavigate("spec")}>FS to TS</button>
          <button className="link active">Code review</button>
          <button className="link" onClick={onLogout}>Log out</button>
        </span>
      </header>
      <div className="messages coach">
        <form className="card coach-card" onSubmit={submit}>
          <h3>Paste ABAP code to review</h3>
          <textarea
            rows={14}
            className="code-input"
            spellCheck={false}
            placeholder={"REPORT zdemo.\nSELECT * FROM vbak INTO TABLE lt_vbak.\nLOOP AT lt_vbak INTO ls_vbak.\n  ...\nENDLOOP."}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={15000}
          />
          <p className="muted small">
            Do not paste code or data you may not share outside your company (client code, customer data). Findings come
            from fixed rules and can be wrong; this does not replace ATC / Code Inspector.
          </p>
          <button type="submit" disabled={busy || code.trim().length < 10}>
            {busy ? "Reviewing..." : "Review code"}
          </button>
        </form>

        {error && <div className="error">{error}</div>}

        {result && (
          <>
            <div className="coach-result">
              <h4>Rule findings ({result.findings.length})</h4>
              {result.findings.length === 0 ? (
                <p className="muted">No rule matched in {result.lines} lines. That does not mean the code is correct.</p>
              ) : (
                <>
                  <p>
                    {counts.map(([s, n]) => (
                      <span key={s} className={`sev sev-${s}`}>{n} {s}</span>
                    ))}
                  </p>
                  {result.findings.map((f, i) => (
                    <Finding key={i} f={f} />
                  ))}
                </>
              )}
            </div>
            <div className="coach-result">
              <h4>Syntax check (abaplint)</h4>
              {!result.syntax_checked ? (
                <p className="muted">abaplint is not installed on this server, so syntax was not checked.</p>
              ) : result.syntax.length === 0 ? (
                <p>No grammar or declaration errors found.</p>
              ) : (
                <ul className="points">
                  {result.syntax.map((s, i) => (
                    <li key={i} className="miss">Line {s.line}: {s.message}</li>
                  ))}
                </ul>
              )}
            </div>
            {result.review && (
              <div className="coach-result">
                <h4>AI review</h4>
                <Markdown>{result.review}</Markdown>
              </div>
            )}
            <p className="muted small">{result.note}</p>
          </>
        )}
      </div>
    </div>
  );
}
