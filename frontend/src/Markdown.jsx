import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Code block with a language label and a copy button.
function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);

  // react-markdown renders fenced code as <pre><code className="language-xyz">text</code></pre>
  const codeEl = Array.isArray(children) ? children[0] : children;
  const className = codeEl?.props?.className || "";
  const language = (className.match(/language-([\w-]+)/) || [])[1] || "code";
  const text = String(codeEl?.props?.children ?? "").replace(/\n$/, "");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard can be blocked; ignore */
    }
  }

  return (
    <div className="codeblock">
      <div className="codeblock-bar">
        <span>{language}</span>
        <button type="button" onClick={copy}>
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <pre>
        <code>{text}</code>
      </pre>
    </div>
  );
}

// Renders the assistant's Markdown (headings, lists, tables, code).
// Raw HTML inside the text is NOT rendered, so model output cannot inject markup.
export default function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="table-wrap">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
