import { useMemo } from "react";
import { inr, inrSigned } from "../lib/format";

export interface BridgeStep {
  label: string;
  value: number; // absolute for totals; signed change for deltas
  kind: "total" | "delta";
}

/**
 * Reconciliation bridge (waterfall). Totals are anchored reference columns;
 * deltas float from the running cumulative. Because a payroll base (~₹31L)
 * dwarfs its month-over-month movement (~₹25K), the value axis is zoomed to the
 * cumulative path (never to zero) so the steps are legible — the totals are
 * labelled in full and a note states the zoom, so nothing is misread.
 */
export function BridgeWaterfall({ steps }: { steps: BridgeStep[] }) {
  const geo = useMemo(() => layout(steps), [steps]);
  if (!geo) return null;
  const { bars, floor, top, zoomed } = geo;

  const W = 960;
  const H = 360;
  const padX = 16;
  const padTop = 34;
  const padBottom = 74;
  const plotH = H - padTop - padBottom;
  const slot = (W - padX * 2) / bars.length;
  const barW = Math.min(78, slot * 0.62);
  const y = (v: number) => padTop + plotH * (1 - (v - floor) / (top - floor));

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[720px] w-full" role="img" aria-label="Reconciliation bridge">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const gy = padTop + plotH * t;
          return <line key={t} x1={padX} x2={W - padX} y1={gy} y2={gy} stroke="hsl(214 32% 91%)" strokeWidth={1} />;
        })}
        {bars.map((b, i) => {
          const cx = padX + slot * i + slot / 2;
          const x = cx - barW / 2;
          const yTop = y(Math.max(b.start, b.end));
          const yBot = y(Math.min(b.start, b.end));
          const h = Math.max(2, yBot - yTop);
          const fill =
            b.kind === "total" ? "#0f2f4c" : b.value >= 0 ? "#0e7490" : "#dc2626";
          const next = bars[i + 1];
          return (
            <g key={i}>
              {next ? (
                <line
                  x1={cx + barW / 2}
                  x2={padX + slot * (i + 1) + slot / 2 - barW / 2}
                  y1={y(next.kind === "total" ? next.end : next.start)}
                  y2={y(next.kind === "total" ? next.end : next.start)}
                  stroke="hsl(215 16% 60%)"
                  strokeDasharray="3 3"
                  strokeWidth={1}
                />
              ) : null}
              <rect x={x} y={yTop} width={barW} height={h} rx={3} fill={fill} opacity={b.value === 0 ? 0.25 : 1} />
              <text x={cx} y={yTop - 8} textAnchor="middle" className="fill-slate-700" fontSize={12} fontWeight={600}>
                {b.kind === "total" ? inr(b.value) : b.value === 0 ? "—" : inrSigned(b.value)}
              </text>
              <text x={cx} y={H - padBottom + 20} textAnchor="middle" className="fill-slate-600" fontSize={12}>
                {wrap(b.label)[0]}
              </text>
              {wrap(b.label)[1] ? (
                <text x={cx} y={H - padBottom + 36} textAnchor="middle" className="fill-slate-600" fontSize={12}>
                  {wrap(b.label)[1]}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      {zoomed ? (
        <p className="mt-1 px-1 text-xs text-muted-foreground">
          Value axis is zoomed to the movement band (not to zero) so the steps are legible; totals are labelled in full.
        </p>
      ) : null}
    </div>
  );
}

function layout(steps: BridgeStep[]) {
  if (steps.length === 0) return null;
  let running = 0;
  const bars = steps.map((s) => {
    if (s.kind === "total") {
      running = s.value;
      return { ...s, start: s.value, end: s.value };
    }
    const start = running;
    running += s.value;
    return { ...s, start, end: running };
  });
  const points = bars.flatMap((b) => [b.start, b.end]);
  const lo = Math.min(...points);
  const hi = Math.max(...points);
  const span = hi - lo || Math.abs(hi) || 1;
  const floor = lo - span * 0.12;
  const top = hi + span * 0.18;
  return { bars, floor, top, zoomed: floor > 0 };
}

function wrap(label: string): [string, string?] {
  if (label.length <= 12) return [label];
  const words = label.split(" ");
  if (words.length === 1) return [label];
  const mid = Math.ceil(words.length / 2);
  return [words.slice(0, mid).join(" "), words.slice(mid).join(" ")];
}
