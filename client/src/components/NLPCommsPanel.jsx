import { Link } from "react-router-dom";
import LiveRadioConsole from "@/components/LiveRadioConsole";

export default function NLPCommsPanel() {
  return <div className="shrink-0 space-y-2">
    <LiveRadioConsole />
    <Link to="/radio" className="block px-3 text-xs underline" style={{ color: "var(--teal)" }}>Open radio workspace and sample recordings →</Link>
  </div>;
}
