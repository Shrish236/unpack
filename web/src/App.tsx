import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import Home from "./pages/Home";
import HomeV1 from "./pages/HomeV1";
import HomeA from "./pages/HomeA";
import HomeB from "./pages/HomeB";
import Cast1 from "./pages/Cast1";
import Cast2 from "./pages/Cast2";
import Cast3 from "./pages/Cast3";
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

// Supports hash routes (#/home-4) as well as direct pathnames (/home-4).
function useRoute(): string {
  const read = () => {
    const hash = location.hash.replace(/^#/, "");
    if (hash) return hash;
    const p = location.pathname.replace(/\/+$/, "");
    if (/^\/home-\d+$/.test(p)) return p;
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

// Home concepts, numbered in the order they were made. `#/` is the isometric home whose hero loops through the six steps.
//  1 original PR-comprehension home    2 product-surface scene       3 Monday to Monday
//  4-8 motion studies (morph, topology, 2.5D stack, state machine, film)
//  9-12 story-led (Groundhog Day, new hire, 2am pager, three seats)   13-15 cast-led (orbit, studio, road)
//  16 the earlier `#/`: hero scene idles on one miniature loop (no per-step callouts)
const HOMES: Record<string, () => React.ReactNode> = {
  "/home-1": () => <HomeV1 />, "/home-2": () => <HomeA />, "/home-3": () => <HomeB />,
  "/home-4": () => <HomeDesign1 />, "/home-5": () => <HomeDesign2 />, "/home-6": () => <HomeDesign3 />,
  "/home-7": () => <HomeDesign4 />, "/home-8": () => <HomeDesign5 />,
  "/home-9": () => <Story1 />, "/home-10": () => <Story2 />, "/home-11": () => <Story3 />, "/home-12": () => <Story4 />,
  "/home-13": () => <Cast1 />, "/home-14": () => <Cast2 />, "/home-15": () => <Cast3 />,
  "/home-16": () => <Home />,
};

function renderRoute(route: string) {
  const home = HOMES[route];
  if (home) return home();
  if (route.startsWith("/pr")) return <PrPage id={route.split("/")[2]} />;
  if (route === "/exec") return <Exec />;
  if (route === "/team") return <Team />;
  if (route === "/govern") return <Govern />;
  return <Home live />;
}

export default function App() {
  const route = useRoute();
  const [theme, toggle] = useTheme();
  const isHomeFamily = route === "/" || /^\/home-\d+$/.test(route);

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
      {renderRoute(route)}
    </>
  );
}
