import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import Home from "./pages/Home";
import HomeV1 from "./pages/HomeV1";
import PrPage from "./pages/PrPage";
import Exec from "./pages/Exec";
import Team from "./pages/Team";
import Govern from "./pages/Govern";
import "./styles/base.css";


type Theme = "light" | "dark";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme === "dark" ? "dark" : "light"));
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("unpack-theme", next); } catch { /* private mode */ }
    setTheme(next);
  };
  return [theme, toggle];
}

// Hash routes only: the server serves this bundle at /a/*, and these are mocks.
function useRoute(): string {
  const read = () => (location.hash.replace(/^#/, "") || "/");
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function Mark({ size = 26 }: { size?: number }) {
  // Two offset squares: the agent's voice and the human's, overlapping like a diff.
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" aria-hidden="true">
      <rect x="1" y="1" width="16" height="16" rx="4" fill="var(--agent)" />
      <rect x="9" y="9" width="16" height="16" rx="4" fill="var(--human)" fillOpacity="0.92" />
    </svg>
  );
}

export default function App() {
  const route = useRoute();
  const [theme, toggle] = useTheme();

  useEffect(() => { document.body.dataset.ready = "true"; }, []); // static-render signal used by the server

  return (
    <>
      <header className="nav">
        <div className="wrap nav-in">
          <a className="brand" href="#/"><Mark />unpack</a>
          <nav className="nav-links" aria-label="Main">
            <a href="#/" aria-current={route === "/" ? "page" : undefined}>Product</a>
            <a href="#/exec" aria-current={route === "/exec" ? "page" : undefined}>Executive</a>
            <a href="#/team" aria-current={route === "/team" ? "page" : undefined}>Managers</a>
            <a href="#/govern" aria-current={route === "/govern" ? "page" : undefined}>Governance</a>
            <a href="#/pr" aria-current={route.startsWith("/pr") ? "page" : undefined}>PR analyses</a>
          </nav>
          <div className="nav-end">
            <button className="btn icon-btn" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <a className="btn primary" href="#/govern">Governance inbox</a>
          </div>
        </div>
      </header>
      {route === "/home-v1" ? <HomeV1 /> : route.startsWith("/pr") ? <PrPage id={route.split("/")[2]} /> : route === "/exec" ? <Exec /> : route === "/team" ? <Team /> : route === "/govern" ? <Govern /> : <Home />}
    </>
  );
}
