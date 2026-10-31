const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}, token) {
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail);
  }
  return res.json();
}

export function register(email, password, fullName) {
  return request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName }),
  });
}

export function login(email, password) {
  // The backend uses the OAuth2 form format: the email goes in the "username" field.
  const body = new URLSearchParams({ username: email, password });
  return request("/auth/login", { method: "POST", body });
}

export function sendMessage(message, token) {
  return request(
    "/chat",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    },
    token
  );
}

export function getHistory(token) {
  return request("/chat/history", {}, token);
}

export function getInterviewTopics(token) {
  return request("/interview/topics", {}, token);
}

export function getInterviewQuestion(filters, token) {
  return request(
    "/interview/question",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(filters) },
    token
  );
}

export function submitInterviewAnswer(questionId, answer, token) {
  return request(
    "/interview/answer",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: questionId, answer }),
    },
    token
  );
}

export function getInterviewProgress(token) {
  return request("/interview/progress", {}, token);
}

export function analyzeError(text, token) {
  return request(
    "/errors/analyze",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    },
    token
  );
}

export function generateSpec(fsText, token) {
  return request(
    "/spec/generate",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fs_text: fsText }),
    },
    token
  );
}

export function reviewCode(code, token) {
  return request(
    "/review/code",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    },
    token
  );
}

// Used by the login page to detect a sleeping free-tier server. Resolves true when /health answers.
export async function pingServer(timeoutMs = 75000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}/health`, { signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}
