import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import Home from "./pages/Home";
import HomeV1 from "./pages/HomeV1";
import HomeA from "./pages/HomeA";
import HomeB from "./pages/HomeB";
import Story1 from "./pages/Story1";
import Story2 from "./pages/Story2";
import Story3 from "./pages/Story3";
import Story4 from "./pages/Story4";
import { HomeDesign1, HomeDesign2, HomeDesign3, HomeDesign4, HomeDesign5 } from "./pages/HomeDesigns";
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

// Supports hash routes (#/home-design-1) as well as direct pathnames (/home-design-1, /hoeme-design-1).
function useRoute(): string {
  const read = () => {
    const hash = location.hash.replace(/^#/, "");
    if (hash) return hash;
    const p = location.pathname.replace(/\/+$/, "");
    if (/^\/(home|hoeme)-design-[1-5]$/.test(p)) return p;
    return "/";
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    window.addEventListener("popstate", on);
    return () => {
      window.removeEventListener("hashchange", on);
      window.removeEventListener("popstate", on);
    };
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

function renderRoute(route: string) {
  const norm = route.replace(/^\/hoeme-design-/, "/home-design-");
  if (norm === "/home-design-1") return <HomeDesign1 />;
  if (norm === "/home-design-2") return <HomeDesign2 />;
  if (norm === "/home-design-3") return <HomeDesign3 />;
  if (norm === "/home-design-4") return <HomeDesign4 />;
  if (norm === "/home-design-5") return <HomeDesign5 />;
  if (route === "/home-v1") return <HomeV1 />;
  if (route === "/home-a") return <HomeA />;
  if (route === "/home-b") return <HomeB />;
  if (route === "/story-1") return <Story1 />;
  if (route === "/story-2") return <Story2 />;
  if (route === "/story-3") return <Story3 />;
  if (route === "/story-4") return <Story4 />;
  if (route.startsWith("/pr")) return <PrPage id={route.split("/")[2]} />;
  if (route === "/exec") return <Exec />;
  if (route === "/team") return <Team />;
  if (route === "/govern") return <Govern />;
  return <Home />;
}

export default function App() {
  const route = useRoute();
  const [theme, toggle] = useTheme();
  const isHomeFamily = route === "/" || /^\/(home|hoeme)-design-[1-5]$/.test(route);

  useEffect(() => { document.body.dataset.ready = "true"; }, []); // static-render signal used by the server

  return (
    <>
      <header className="nav">
        <div className="wrap nav-in">
          <a className="brand" href="#/"><Mark />unpack</a>
          <nav className="nav-links" aria-label="Main">
            <a href="#/" aria-current={isHomeFamily ? "page" : undefined}>Product</a>
            <a href="#/exec" aria-current={route === "/exec" ? "page" : undefined}>Executive</a>
            <a href="#/team" aria-current={route === "/team" ? "page" : undefined}>Managers</a>
            <a href="#/govern" aria-current={route === "/govern" ? "page" : undefined}>Governance</a>
            <a href="#/pr" aria-current={route.startsWith("/pr") ? "page" : undefined}>PR example</a>
          </nav>
          <div className="nav-end">
            <button className="btn icon-btn" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <a className="btn primary" href="#/govern">Governance inbox</a>
          </div>
        </div>
      </header>
      {renderRoute(route)}
    </>
  );
}
