import React, { useEffect, useState } from "react";

export default function App() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Signal to Chromium / Playwright screenshot renderer that data is loaded
    document.body.dataset.ready = "true";
    setReady(true);
  }, []);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <header>
        <h1>🧭 Unpack</h1>
        <p>Interactive code reasoning and knowledge graph view for AI agent pull requests.</p>
      </header>
      <main style={{ marginTop: "2rem" }}>
        <div style={{ padding: "1.5rem", border: "1px solid #e2e8f0", borderRadius: "8px" }}>
          <h3>Base Web UI Initialized</h3>
          <p>Ready state: <strong>{ready ? "data-ready=true" : "loading..."}</strong></p>
        </div>
      </main>
    </div>
  );
}
