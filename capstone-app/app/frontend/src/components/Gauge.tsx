import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type Tone = "green" | "amber" | "alert";

const TONE = {
  green: { stroke: "#39FF9A", glow: "rgba(57,255,154,0.55)" },
  amber: { stroke: "#FFB000", glow: "rgba(255,176,0,0.55)" },
  alert: { stroke: "#FF3B30", glow: "rgba(255,59,48,0.6)" },
} as const;

interface GaugeProps {
  /** 0..1 fraction of the arc filled. */
  value: number;
  label: string;
  /** Big luminous readout in the dial center. */
  readout: string;
  tone?: Tone;
  /** Small caption under the readout (e.g. units). */
  sub?: string;
  size?: number;
}

/**
 * Round instrument gauge with a damped needle sweep — the signature
 * night-flight element. The arc spans 270° (aviation dial convention),
 * the needle eases to its value on mount/change, and tick marks ring the face.
 */
export function Gauge({ value, label, readout, tone = "green", sub, size = 148 }: GaugeProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const [shown, setShown] = useState(0);
  const raf = useRef<number>();

  useEffect(() => {
    const start = performance.now();
    const from = shown;
    const dur = 900;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      // easeOutCubic — a damped physical settle, never a snap.
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(from + (clamped - from) * eased);
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current!);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clamped]);

  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 14;
  const START = 135; // degrees; sweep 270° clockwise
  const SWEEP = 270;
  const { stroke, glow } = TONE[tone];

  const polar = (deg: number, radius: number) => {
    const rad = ((deg - 90) * Math.PI) / 180;
    return [cx + radius * Math.cos(rad), cy + radius * Math.sin(rad)];
  };
  const arcPath = (frac: number) => {
    const end = START + SWEEP * frac;
    const [x0, y0] = polar(START, r);
    const [x1, y1] = polar(end, r);
    const large = SWEEP * frac > 180 ? 1 : 0;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
  };
  const needleDeg = START + SWEEP * shown;
  // Needle is an OUTER pointer: it rides just inside the arc and stops well
  // short of center, so the dial center stays clear for the readout text.
  const [nx, ny] = polar(needleDeg, r - 4); // tip near the rim
  const [nbx, nby] = polar(needleDeg, r - 34); // tail — never reaches center
  const ticks = Array.from({ length: 10 }, (_, i) => START + (SWEEP * i) / 9);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="block">
        {/* tick ring */}
        {ticks.map((deg, i) => {
          const [ox, oy] = polar(deg, r + 3);
          const [ix, iy] = polar(deg, r - 3);
          return (
            <line
              key={i}
              x1={ox}
              y1={oy}
              x2={ix}
              y2={iy}
              stroke="#6B7580"
              strokeWidth={1.5}
              opacity={0.55}
            />
          );
        })}
        {/* track */}
        <path d={arcPath(1)} fill="none" stroke="#1A1E22" strokeWidth={7} strokeLinecap="round" />
        {/* value arc */}
        <path
          d={arcPath(shown)}
          fill="none"
          stroke={stroke}
          strokeWidth={7}
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 5px ${glow})` }}
        />
        {/* needle — outer pointer, stops short of center (readout lives there) */}
        <line
          x1={nbx}
          y1={nby}
          x2={nx}
          y2={ny}
          stroke={stroke}
          strokeWidth={3}
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 4px ${glow})` }}
        />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span
            className={cn("readout text-2xl font-bold leading-none")}
            style={{ color: stroke, textShadow: `0 0 8px ${glow}` }}
          >
            {readout}
          </span>
          {sub && <span className="placard mt-1 !text-[10px]">{sub}</span>}
        </div>
      </div>
      <span className="placard">{label}</span>
    </div>
  );
}
