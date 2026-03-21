import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Bell, Plane, Sparkles } from "lucide-react";

export default function TopBar() {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const utc = time.toISOString().slice(11, 19);

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between h-[57px] px-4 bg-atc-bg/95 backdrop-blur-md border-b border-atc-cyan/10">
      {/* Left — Logo */}
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-atc-cyan/10 border border-atc-cyan/20">
          <Plane className="w-5 h-5 text-atc-cyan" />
        </div>
        <div>
          <h1 className="text-sm font-bold tracking-widest text-atc-text-primary">AEROSYNC ATC</h1>
          <p className="text-[10px] text-atc-text-muted tracking-wide">Air Traffic Controller Assistant v2.4.1</p>
        </div>
      </div>

      {/* Center — Status + Clock */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-2 px-3 py-1 rounded-full border border-atc-success/30 bg-atc-success/5">
          <span className="w-2 h-2 rounded-full bg-atc-success animate-pulse-dot" />
          <span className="text-[10px] font-mono tracking-wider text-atc-success uppercase">System Active — All Systems Nominal</span>
        </div>
        <div className="font-mono text-lg tracking-widest text-atc-cyan glow-cyan">
          {utc} <span className="text-[10px] text-atc-text-muted">UTC</span>
        </div>
      </div>

      {/* Right — Alerts + AI + Controller */}
      <div className="flex items-center gap-3">
        <Badge variant="destructive" className="flex items-center gap-1.5 animate-blink bg-atc-danger/20 text-atc-danger border border-atc-danger/40 hover:bg-atc-danger/30">
          <Bell className="w-3 h-3" />
          <span className="text-[10px] font-mono tracking-wider">2 ALERTS</span>
        </Badge>

        <Badge className="flex items-center gap-1.5 bg-atc-purple/10 text-atc-purple border border-atc-purple/30 hover:bg-atc-purple/20">
          <Sparkles className="w-3 h-3" />
          <span className="text-[10px] font-mono tracking-wider">AI ASSIST ON</span>
        </Badge>

        <div className="text-right ml-2">
          <p className="text-xs font-semibold text-atc-text-primary tracking-wide">A. SHARMA</p>
          <p className="text-[10px] text-atc-text-muted font-mono">SECTOR: 7B-ALPHA</p>
        </div>
      </div>
    </header>
  );
}
