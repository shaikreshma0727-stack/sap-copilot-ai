import { useEffect, useState } from "react";
import {
  getInterviewProgress,
  getInterviewQuestion,
  getInterviewTopics,
  submitInterviewAnswer,
} from "./api.js";

function Progress({ progress }) {
  if (!progress) return null;
  if (progress.attempts === 0) {
    return <p className="muted">No answers yet. Answer a question and your progress shows up here.</p>;
  }
  return (
    <div className="coach-progress">
      <div>
        <strong>{progress.attempts}</strong> answers, average <strong>{progress.average}</strong> / {progress.max_score}
      </div>
      <table>
        <thead>
          <tr>
            <th>Topic</th>
            <th>Answers</th>
            <th>Average</th>
          </tr>
        </thead>
        <tbody>
          {progress.by_topic.map((t) => (
            <tr key={t.topic}>
              <td>{t.topic}</td>
              <td>{t.attempts}</td>
              <td>{t.average}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {progress.weakest.length > 0 && (
        <p>
          Practise next: <strong>{progress.weakest.join(", ")}</strong>
        </p>
      )}
    </div>
  );
}

function Result({ result }) {
  return (
    <div className="coach-result">
      <div className="coach-score">
        {result.score} <span className="muted">/ {result.max_score}</span>
      </div>
      {result.covered.length > 0 && (
        <>
          <h4>Points you covered</h4>
          <ul className="points">
            {result.covered.map((c, i) => (
              <li key={i} className="ok">
                {c.text} {c.by === "ai" && <span className="tag">AI judged</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {result.missed.length > 0 && (
        <>
          <h4>Points missing</h4>
          <ul className="points">
            {result.missed.map((m, i) => (
              <li key={i} className="miss">
                {m}
              </li>
            ))}
          </ul>
        </>
      )}
      {result.feedback && (
        <>
          <h4>Feedback</h4>
          <p>{result.feedback}</p>
        </>
      )}
      <details>
        <summary>Model answer</summary>
        <p>{result.model_answer}</p>
      </details>
      <p className="muted small">{result.scoring_note}</p>
    </div>
  );
}

export default function InterviewCoach({ token, onLogout, onNavigate }) {
  const [topics, setTopics] = useState([]);
  const [topic, setTopic] = useState("");
  const [level, setLevel] = useState("");
  const [question, setQuestion] = useState(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function fail(err) {
    if (err.message.toLowerCase().includes("token")) onLogout();
    else setError(err.message);
  }

  async function refreshProgress() {
    try {
      setProgress(await getInterviewProgress(token));
    } catch (err) {
      fail(err);
    }
  }

  useEffect(() => {
    getInterviewTopics(token).then(setTopics).catch(fail);
    refreshProgress();
  }, [token]);

  async function nextQuestion() {
    setError("");
    setResult(null);
    setAnswer("");
    setBusy(true);
    try {
      const filters = {};
      if (topic) filters.topic = topic;
      if (level) filters.level = level;
      if (question) filters.exclude_id = question.id;
      setQuestion(await getInterviewQuestion(filters, token));
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    if (!question || !answer.trim() || busy) return;
    setError("");
    setBusy(true);
    try {
      setResult(await submitInterviewAnswer(question.id, answer, token));
      await refreshProgress();
    } catch (err) {
      fail(err);
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
          <button className="link active">Interview coach</button>
          <button className="link" onClick={() => onNavigate("errors")}>Error analyzer</button>
          <button className="link" onClick={() => onNavigate("spec")}>FS to TS</button>
          <button className="link" onClick={() => onNavigate("review")}>Code review</button>
          <button className="link" onClick={onLogout}>Log out</button>
        </span>
      </header>
      <div className="messages coach">
        <div className="coach-filters">
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            <option value="">All topics</option>
            {topics.map((t) => (
              <option key={t.topic} value={t.topic}>
                {t.topic} ({t.count})
              </option>
            ))}
          </select>
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">All levels</option>
            <option value="basic">Basic</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
          </select>
          <button onClick={nextQuestion} disabled={busy}>
            {question ? "Next question" : "Start"}
          </button>
        </div>

        {error && <div className="error">{error}</div>}

        {!question && (
          <p className="muted center">
            Pick a topic and press Start. Answer in your own words, as in a real interview. The score shows how many
            of the expected key points you covered.
          </p>
        )}

        {question && (
          <form className="card coach-card" onSubmit={submit}>
            <div className="agent">
              {question.topic} - {question.level}
            </div>
            <h3>{question.question}</h3>
            <textarea
              rows={6}
              placeholder="Type your answer..."
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              disabled={busy || !!result}
            />
            {!result && (
              <button type="submit" disabled={busy || !answer.trim()}>
                {busy ? "Checking..." : "Submit answer"}
              </button>
            )}
          </form>
        )}

        {result && <Result result={result} />}

        <h3>Your progress</h3>
        <Progress progress={progress} />
      </div>
    </div>
  );
}
