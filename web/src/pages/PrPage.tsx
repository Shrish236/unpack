import PrLive from "../pr/PrLive";
import PrMock from "./PrMock";
import { DEFAULT_ANALYSIS } from "../api";

// #/pr -> default live analysis, #/pr/<public_id> -> that analysis, #/pr/mock -> the illustrative page.
export default function PrPage({ id }: { id?: string }) {
  if (id === "mock") return <PrMock />;
  return <PrLive key={id ?? DEFAULT_ANALYSIS} id={id || DEFAULT_ANALYSIS} />;
}
