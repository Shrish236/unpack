import type { CSSProperties } from "react";
import Person from "./Person";

// ~14s loop. Default styles are the finished frame (clock 02:14, recovered, cards visible), so reduced motion shows the answer.
const wall = Array.from({ length: 11 }, (_, k) => ({ w: 38 + ((k * 47) % 58), kind: k % 4 === 1 ? "del" : k % 3 === 0 ? "ctx" : "add" }));
const cards: [string, string, "agent" | "human", string][] = [
  ["Agent", "retry forever", "agent", "T22"],
  ["You", "cap at 5", "human", "T33"],
  ["Agent", "skip flaky test", "agent", "T31"],
  ["Agent claim", "full coverage", "agent", "T47"],
];

export default function HeroScene() {
  return (
    <div className="s3-scene" role="img" aria-label="At 02:07 an alert fires. The on-call engineer opens a wall of agent-written diff, which unfolds into four decisions. The unsupported claim is found at 02:14, and the next morning a tech lead makes the fix a rule.">
      <i className="s3-moon" />
      <header className="s3-bar">
        <div className="s3-clock mono"><span className="s3-t1">02:07</span><span className="s3-t2">02:14</span></div>
        <div className="s3-alert mono"><span className="s3-bad">● payments-api · errors 14%</span><span className="s3-good">● payments-api · recovered</span></div>
      </header>
      <div className="s3-body">
        <div className="s3-who">
          <i className="s3-phone" />
          <div className="s3-person"><Person size={34} /><i className="s3-sweat" /><i className="s3-calm">✓</i></div>
          <span className="s3-role mono">On-call</span>
        </div>
        <div className="s3-pr">
          <div className="s3-prh mono">PR #482 · +1,204 −311 · agent-written</div>
          <div className="s3-wall">{wall.map((b, k) => <i key={k} className={b.kind} style={{ width: `${b.w}%` }} />)}</div>
          <ol className="s3-cards">
            {cards.map(([who, what, tone, turn], k) => (
              <li key={turn} className={`s3-card ${tone} ${k === 3 ? "claim" : ""}`} style={{ ["--k" as string]: k } as CSSProperties}>
                <b className="mono">{who}</b><span>{what}</span><em className="mono">{k === 3 ? "unsupported" : turn}</em>
                {(k === 0 || k === 2) && <i className="s3-strike" />}
              </li>
            ))}
          </ol>
          <span className="s3-point mono">◀ found it</span>
          <span className="s3-found mono">✓ 02:14</span>
        </div>
      </div>
      <footer className="s3-morning"><Person size={22} tone="human" /><span className="mono">Tech lead · next morning</span><b className="s3-chip mono">P-13 · cap retries at 5</b></footer>
    </div>
  );
}
