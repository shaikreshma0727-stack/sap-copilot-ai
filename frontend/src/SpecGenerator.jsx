import { useState } from "react";
import { generateSpec } from "./api.js";
import Markdown from "./Markdown.jsx";

function Topics({ topics, coverage }) {
  return (
    <>
      <p>
        <strong>{coverage}</strong>
      </p>
      <ul className="points">
        {topics.map((t) => (
          <li key={t.id} className={t.mentioned ? "ok" : "miss"}>
            {t.label}
            {!t.mentioned && <div className="muted small">Ask: {t.question}</div>}
          </li>
        ))}
      </ul>
    </>
  );
}

function Objects({ detected }) {
  const { catalog_objects: known, custom_objects: custom, type_hint: hint } = detected;
  if (!hint && known.length === 0 && custom.length === 0) {
    return <p className="muted">No SAP object names recognised in the text.</p>;
  }
  return (
    <>
      {hint && (
        <p>
          Looks like: <strong>{hint}</strong> <span className="muted small">(keyword hint only)</span>
        </p>
      )}
      {known.length > 0 && (
        <p>
          In the catalog:{" "}
          {known.map((o) => (
            <span key={o.name} className="tcode">
              {o.name} <span className="tag">{o.status}</span>
            </span>
          ))}
        </p>
      )}
      {custom.length > 0 && (
        <p>
          Custom names:{" "}
          {custom.map((c) => (
            <code key={c} className="tcode">{c}</code>
          ))}
        </p>
      )}
    </>
  );
}

export default function SpecGenerator({ token, onLogout, onNavigate }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (text.trim().length < 40 || busy) return;
    setError("");
    setResult(null);
    setBusy(true);
    try {
      setResult(await generateSpec(text, token));
    } catch (err) {
      if (err.message.toLowerCase().includes("token")) onLogout();
      else setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function copyDraft() {
    try {
      await navigator.clipboard.writeText(result.draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard can be blocked; the text is still on screen */
    }
  }

  return (
    <div className="chat">
      <header>
        <strong>SAP Copilot AI</strong>
        <span className="nav">
          <button className="link" onClick={() => onNavigate("chat")}>Chat</button>
          <button className="link" onClick={() => onNavigate("coach")}>Interview coach</button>
          <button className="link" onClick={() => onNavigate("errors")}>Error analyzer</button>
          <button className="link active">FS to TS</button>
          <button className="link" onClick={onLogout}>Log out</button>
        </span>
      </header>
      <div className="messages coach">
        <form className="card coach-card" onSubmit={submit}>
          <h3>Paste a functional specification (FS)</h3>
          <textarea
            rows={12}
            placeholder={"Purpose: ...\nSelection screen: ...\nData: ...\nOutput: ..."}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={15000}
          />
          <p className="muted small">
            Do not paste confidential customer data or text you may not share outside your company. The topic check
            below is a fixed checklist, the draft is written by an AI from your text only.
          </p>
          <button type="submit" disabled={busy || text.trim().length < 40}>
            {busy ? "Working..." : "Check FS and draft TS"}
          </button>
        </form>

        {error && <div className="error">{error}</div>}

        {result && (
          <>
            <div className="coach-result">
              <h4>What the FS mentions</h4>
              <Topics topics={result.topics} coverage={result.coverage} />
            </div>
            <div className="coach-result">
              <h4>SAP objects found</h4>
              <Objects detected={result.detected} />
            </div>
            {result.draft && (
              <div className="coach-result">
                <h4>
                  TS draft{" "}
                  <button type="button" className="link" onClick={copyDraft}>
                    {copied ? "Copied" : "Copy Markdown"}
                  </button>
                </h4>
                <Markdown>{result.draft}</Markdown>
              </div>
            )}
            <p className="muted small">{result.note}</p>
          </>
        )}
      </div>
    </div>
  );
}
