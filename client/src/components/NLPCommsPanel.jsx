import { nlpComms } from "@/data/mockData";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Radio, Bot, Mic, Headphones } from "lucide-react";

const TYPE_CONFIG = {
  atc: { label: "ATC", color: "#00c8ff", icon: Headphones, bg: "bg-atc-cyan/5 border-atc-cyan/15" },
  pilot: { label: "PILOT", color: "#a855f7", icon: Mic, bg: "bg-atc-purple/5 border-atc-purple/15" },
  ai: { label: "AI SYSTEM", color: "#00ffc8", icon: Bot, bg: "bg-atc-green/5 border-atc-green/15" },
};

export default function NLPCommsPanel() {
  return (
    <div className="rounded-lg border border-atc-cyan/10 bg-atc-panel/50 flex flex-col">
      <div className="p-3 border-b border-atc-cyan/10">
        <h3 className="text-[10px] font-bold tracking-widest text-atc-text-muted uppercase flex items-center gap-1.5">
          <Radio className="w-3 h-3 text-atc-cyan" />
          NLP Comms Feed
        </h3>
        <p className="text-[8px] text-atc-text-muted/60 mt-0.5">AI-assisted communication transcript</p>
      </div>

      <ScrollArea className="flex-1 max-h-[300px]">
        <div className="p-2 space-y-1.5">
          {nlpComms.map((msg, i) => {
            const cfg = TYPE_CONFIG[msg.type] || TYPE_CONFIG.atc;
            const Icon = cfg.icon;

            return (
              <div key={i} className={`rounded-md border p-2.5 ${cfg.bg}`}>
                <div className="flex items-center gap-2 mb-1">
                  <Icon className="w-3 h-3" style={{ color: cfg.color }} />
                  <span className="text-[8px] font-mono font-bold tracking-wider" style={{ color: cfg.color }}>
                    {msg.type === "ai" ? cfg.label : `${cfg.label} — ${msg.flight}`}
                  </span>
                  <span className="text-[8px] font-mono text-atc-text-muted/50 ml-auto">{msg.time}</span>
                  {msg.aiTranscribed && (
                    <span className="text-[7px] font-mono text-atc-green/40 px-1 rounded bg-atc-green/5">AI-T</span>
                  )}
                </div>
                <p className="text-[10px] text-atc-text-secondary leading-relaxed pl-5">{msg.text}</p>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
