import HomeShell from "./HomeShell";
import Design1Morph from "./designs/Design1Morph";
import Design2Topology from "./designs/Design2Topology";
import Design3Stack from "./designs/Design3Stack";
import Design4StateMachine from "./designs/Design4StateMachine";
import Design5Film from "./designs/Design5Film";

export function HomeDesign1() {
  return (
    <HomeShell
      activeDesign={1}
      designName="Morphing Product Artifact"
      designTag="motion/react layoutId springs"
      hideStepVizDesktop
      renderStage={(step) => <Design1Morph step={step} />}
    />
  );
}

export function HomeDesign2() {
  return (
    <HomeShell
      activeDesign={2}
      designName="Living Signal Topology"
      designTag="60fps Canvas 2D physics + HUD"
      renderStage={(step) => <Design2Topology step={step} />}
    />
  );
}

export function HomeDesign3() {
  return (
    <HomeShell
      activeDesign={3}
      designName="Exploded 2.5D Architectural Stack"
      designTag="CSS preserve-3d · 4 planes of truth"
      renderStage={(step) => <Design3Stack step={step} />}
    />
  );
}

export function HomeDesign4() {
  return (
    <HomeShell
      activeDesign={4}
      designName="Editorial Vector State Machine"
      designTag="Rive-style procedural spring engine"
      renderStage={(step) => <Design4StateMachine step={step} />}
    />
  );
}

export function HomeDesign5() {
  return (
    <HomeShell
      activeDesign={5}
      designName="Programmatic Motion Film"
      designTag="Remotion-style 60fps chapter player"
      hideStepVizDesktop
      renderStage={(step) => <Design5Film step={step} />}
    />
  );
}
