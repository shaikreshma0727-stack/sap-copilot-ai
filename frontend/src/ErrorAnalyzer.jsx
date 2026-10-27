import { useState } from "react";
import { analyzeError } from "./api.js";
import Markdown from "./Markdown.jsx";

const FIELD_LABELS = {
  runtime_error: "Runtime error",
  exception: "Exception",
  short_text: "Short text",
  program: "Program",
  include: "Include",
  line: "Line",
  message_class: "Message class",
  message_number: "Message number",
  transaction: "Transaction",
};

function Facts({ parsed }) {
  const rows = Object.keys(FIELD_LABELS).filter((k) => parsed[k] !== null && parsed[k] !== undefined);
  if (rows.length === 0) {
    return <p className="muted">Nothing could be read from the text (no runtime error name, program or message number found).</p>;
  }
  return (
    <table className="facts">
      <tbody>
        {rows.map((k) => (
          <tr key={k}>
            <th>{FIELD_LABELS[k]}</th>
            <td>{String(parsed[k])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MatchCard({ m }) {
  return (
    <details className="err-match" open>
      <summary>
        {m.title} <span className="tag">{m.status}</span>
      </summary>
      <h4>Possible causes</h4>
      <ul>
        {m.causes.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
      <h4>What to do</h4>
      <ol>
        {m.fix_steps.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ol>
      {m.tcodes.length > 0 && (
        <p>
          Check: {m.tcodes.map((t) => (
            <code key={t} className="tcode">{t}</code>
          ))}
        </p>
      )}
      <p className="muted small">Source: {m.source}</p>
    </details>
  );
}

export default function ErrorAnalyzer({ token, onLogout, onNavigate }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (text.trim().length < 3 || busy) return;
    setError("");
    setResult(null);
    setBusy(true);
    try {
      setResult(await analyzeError(text, token));
    } catch (err) {
      if (err.message.toLowerCase().includes("token")) onLogout();
      else setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <header>
        <strong>SAP Copilot AI</strong>
        <span className="nav">
          <button className="link" onClick={() => onNavigate("chat")}>Chat</button>
          <button className="link" onClick={() => onNavigate("coach")}>Interview coach</button>
          <button className="link active">Error analyzer</button>
          <button className="link" onClick={() => onNavigate("spec")}>FS to TS</button>
          <button className="link" onClick={onLogout}>Log out</button>
        </span>
      </header>
      <div className="messages coach">
        <form className="card coach-card" onSubmit={submit}>
          <h3>Paste an ST22 dump or an SAP error message</h3>
          <textarea
            rows={10}
            placeholder={'Runtime Errors  TIME_OUT\nShort text\n    Time limit exceeded.\n...'}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={20000}
          />
          <p className="muted small">
            Do not paste passwords or confidential customer data. Remove anything you are not allowed to share
            outside your company.
          </p>
          <button type="submit" disabled={busy || text.trim().length < 3}>
            {busy ? "Analyzing..." : "Analyze"}
          </button>
        </form>

        {error && <div className="error">{error}</div>}

        {result && (
          <>
            <div className="coach-result">
              <h4>Read from your text</h4>
              <Facts parsed={result.parsed} />
            </div>
            {result.matches.length > 0 && (
              <div className="coach-result">
                <h4>Matching knowledge</h4>
                {result.matches.map((m) => (
                  <MatchCard key={m.id} m={m} />
                ))}
              </div>
            )}
            {result.explanation && (
              <div className="coach-result">
                <h4>AI explanation</h4>
                <Markdown>{result.explanation}</Markdown>
              </div>
            )}
            <p className="muted small">{result.note}</p>
          </>
        )}
      </div>
    </div>
  );
}
