import React, { useState } from 'react';

/* ─────────────────────────────────────────────────────────────────────────────
   1. DONUT / RING CHART (Pure SVG, Responsive, Zero Dependencies)
   ───────────────────────────────────────────────────────────────────────────── */
export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

export const DonutChart: React.FC<{
  data: DonutSegment[];
  size?: number;
  strokeWidth?: number;
  centerLabel?: string;
  centerValue?: string | number;
  unit?: string;
}> = ({
  data,
  size = 180,
  strokeWidth = 26,
  centerLabel,
  centerValue,
  unit = '',
}) => {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const total = data.reduce((acc, item) => acc + (Number(item.value) || 0), 0);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  let cumulativeOffset = 0;

  return (
    <div className="edu-donut-container d-flex flex-column flex-sm-row align-items-center justify-content-center gap-4 py-2">
      {/* SVG Ring */}
      <div className="position-relative d-inline-flex align-items-center justify-content-center" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="edu-donut-svg">
          {/* Background track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke="#E2E8F0"
            strokeWidth={strokeWidth}
          />
          {total > 0 &&
            data.map((seg, idx) => {
              const val = Number(seg.value) || 0;
              const ratio = val / total;
              const strokeDasharray = `${ratio * circumference} ${circumference}`;
              const strokeDashoffset = -cumulativeOffset;
              cumulativeOffset += ratio * circumference;

              const isHovered = hoveredIdx === idx;

              return (
                <circle
                  key={idx}
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="transparent"
                  stroke={seg.color}
                  strokeWidth={isHovered ? strokeWidth + 4 : strokeWidth}
                  strokeDasharray={strokeDasharray}
                  strokeDashoffset={strokeDashoffset}
                  strokeLinecap="round"
                  className="edu-donut-segment"
                  style={{
                    transition: 'all 0.25s ease',
                    cursor: 'pointer',
                    opacity: hoveredIdx === null || isHovered ? 1 : 0.6,
                  }}
                  onMouseEnter={() => setHoveredIdx(idx)}
                  onMouseLeave={() => setHoveredIdx(null)}
                />
              );
            })}
        </svg>

        {/* Center label & number */}
        <div className="position-absolute text-center d-flex flex-column align-items-center justify-content-center" style={{ pointerEvents: 'none' }}>
          <span className="fw-bold fs-4 lh-1" style={{ color: '#002583' }}>
            {hoveredIdx !== null
              ? `${data[hoveredIdx].value}${unit}`
              : centerValue !== undefined
              ? `${centerValue}${unit}`
              : `${total}`}
          </span>
          <span className="text-muted mt-1" style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {hoveredIdx !== null ? data[hoveredIdx].label : centerLabel || 'Total'}
          </span>
        </div>
      </div>

      {/* Legend list */}
      <div className="edu-donut-legend d-flex flex-column gap-2" style={{ minWidth: 160 }}>
        {data.map((seg, idx) => {
          const val = Number(seg.value) || 0;
          const pct = total > 0 ? Math.round((val / total) * 100) : 0;
          const isHovered = hoveredIdx === idx;

          return (
            <div
              key={idx}
              className={`d-flex align-items-center justify-content-between p-1.5 rounded-2 ${isHovered ? 'bg-light' : ''}`}
              style={{ cursor: 'pointer', transition: 'background 0.15s ease' }}
              onMouseEnter={() => setHoveredIdx(idx)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              <div className="d-flex align-items-center gap-2">
                <span
                  className="rounded-circle d-inline-block flex-shrink-0"
                  style={{
                    width: 10,
                    height: 10,
                    backgroundColor: seg.color,
                    boxShadow: isHovered ? `0 0 6px ${seg.color}` : 'none',
                  }}
                />
                <span className="small text-secondary text-truncate" style={{ maxWidth: 110 }}>
                  {seg.label}
                </span>
              </div>
              <div className="text-end ps-2">
                <span className="small fw-bold text-dark">{val}</span>
                <span className="small text-muted ms-1" style={{ fontSize: '11px' }}>
                  ({pct}%)
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────────
   2. HORIZONTAL PERFORMANCE BAR CHART (e.g. Subject Averages with Benchmark)
   ───────────────────────────────────────────────────────────────────────────── */
export interface BarItem {
  id?: string | number;
  label: string;
  code?: string;
  value: number; // e.g. 74.5%
  benchmark?: number; // e.g. 50%
  count?: number;
  color?: string;
}

export const HorizontalBarChart: React.FC<{
  data: BarItem[];
  benchmark?: number;
  benchmarkLabel?: string;
  max?: number;
}> = ({ data, benchmark = 50, benchmarkLabel = '50% Pass Benchmark', max = 100 }) => {
  if (!data || data.length === 0) {
    return <div className="text-muted small py-3 text-center">No performance data recorded yet.</div>;
  }

  return (
    <div className="edu-bar-chart-wrap">
      {benchmark !== undefined && (
        <div className="d-flex justify-content-end align-items-center gap-2 mb-3">
          <span className="d-inline-block border-top border-2 border-danger" style={{ width: 18 }} />
          <span className="small text-muted" style={{ fontSize: '11px' }}>
            {benchmarkLabel}
          </span>
        </div>
      )}

      <div className="d-flex flex-column gap-3">
        {data.map((item, idx) => {
          const val = Math.min(max, Math.max(0, item.value || 0));
          const isPassing = val >= benchmark;
          const barColor =
            item.color || (isPassing ? 'linear-gradient(90deg, #002583 0%, #1E40AF 100%)' : 'linear-gradient(90deg, #F59E0B 0%, #D97706 100%)');

          return (
            <div key={item.id ?? idx} className="edu-bar-item">
              <div className="d-flex justify-content-between align-items-center small mb-1">
                <span className="fw-semibold text-dark text-truncate" style={{ maxWidth: '65%' }}>
                  {item.label} {item.code ? `(${item.code})` : ''}
                </span>
                <span className="fw-bold" style={{ color: isPassing ? '#002583' : '#D97706' }}>
                  {val}% {item.count ? <span className="text-muted fw-normal">({item.count} results)</span> : null}
                </span>
              </div>

              <div
                className="position-relative rounded-pill overflow-hidden"
                style={{ height: 10, backgroundColor: '#E2E8F0' }}
              >
                {/* Benchmark indicator line */}
                {benchmark !== undefined && (
                  <div
                    className="position-absolute top-0 bottom-0"
                    style={{
                      left: `${(benchmark / max) * 100}%`,
                      width: 2,
                      backgroundColor: '#EF4444',
                      zIndex: 2,
                    }}
                    title={benchmarkLabel}
                  />
                )}

                {/* Progress bar fill */}
                <div
                  className="h-100 rounded-pill transition-all"
                  style={{
                    width: `${val}%`,
                    background: barColor,
                    transition: 'width 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────────
   3. SPARKLINE / TREND AREA CHART (Pure SVG Curve)
   ───────────────────────────────────────────────────────────────────────────── */
export interface TrendPoint {
  label: string;
  value: number;
}

export const TrendAreaChart: React.FC<{
  data: TrendPoint[];
  height?: number;
  color?: string;
  fillColor?: string;
  unit?: string;
}> = ({
  data,
  height = 140,
  color = '#002583',
  fillColor = 'rgba(0, 37, 131, 0.1)',
  unit = '',
}) => {
  if (!data || data.length < 2) {
    return <div className="text-muted small py-3 text-center">Need at least 2 data points for trend line.</div>;
  }

  const values = data.map((d) => Number(d.value) || 0);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const range = maxVal - minVal || 1;

  const width = 500;
  const paddingX = 20;
  const paddingY = 20;
  const chartW = width - paddingX * 2;
  const chartH = height - paddingY * 2;

  const points = data.map((d, idx) => {
    const x = paddingX + (idx / (data.length - 1)) * chartW;
    const y = paddingY + chartH - ((Number(d.value) - minVal) / range) * chartH;
    return { x, y, ...d };
  });

  // Construct curved SVG path
  let pathD = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i];
    const p1 = points[i + 1];
    const mx = (p0.x + p1.x) / 2;
    pathD += ` C ${mx} ${p0.y}, ${mx} ${p1.y}, ${p1.x} ${p1.y}`;
  }

  const fillD = `${pathD} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;

  return (
    <div className="edu-trend-chart position-relative w-100">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-100" style={{ overflow: 'visible', maxHeight: height }}>
        <defs>
          <linearGradient id={`trendGrad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Fill area */}
        <path d={fillD} fill={`url(#trendGrad-${color.replace('#', '')})`} />

        {/* Line stroke */}
        <path d={pathD} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />

        {/* Data points */}
        {points.map((pt, idx) => (
          <g key={idx}>
            <circle
              cx={pt.x}
              cy={pt.y}
              r="4.5"
              fill="#FFFFFF"
              stroke={color}
              strokeWidth="2.5"
              className="cursor-pointer"
            >
              <title>{`${pt.label}: ${pt.value}${unit}`}</title>
            </circle>
          </g>
        ))}
      </svg>

      {/* X-axis labels */}
      <div className="d-flex justify-content-between text-muted small mt-2" style={{ fontSize: '11px' }}>
        {data.map((d, idx) => (
          <span key={idx} className="text-truncate px-1">
            {d.label}
          </span>
        ))}
      </div>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────────
   4. MULTI-SEGMENT STACKED PROGRESS BAR
   ───────────────────────────────────────────────────────────────────────────── */
export interface StackSegment {
  label: string;
  value: number;
  color: string;
}

export const StackedProgressBar: React.FC<{
  segments: StackSegment[];
  height?: number;
}> = ({ segments, height = 12 }) => {
  const total = segments.reduce((sum, s) => sum + (Number(s.value) || 0), 0);

  if (total === 0) {
    return <div className="text-muted small text-center py-1">No recorded entries.</div>;
  }

  return (
    <div>
      <div
        className="d-flex rounded-pill overflow-hidden w-100"
        style={{ height, backgroundColor: '#E2E8F0' }}
      >
        {segments.map((s, idx) => {
          const pct = Math.round(((Number(s.value) || 0) / total) * 100);
          if (pct === 0) return null;
          return (
            <div
              key={idx}
              style={{
                width: `${pct}%`,
                backgroundColor: s.color,
                transition: 'width 0.4s ease',
              }}
              title={`${s.label}: ${s.value} (${pct}%)`}
            />
          );
        })}
      </div>

      <div className="d-flex flex-wrap gap-3 mt-2">
        {segments.map((s, idx) => {
          const val = Number(s.value) || 0;
          const pct = Math.round((val / total) * 100);
          return (
            <div key={idx} className="d-flex align-items-center gap-1.5 small">
              <span className="rounded-circle d-inline-block" style={{ width: 8, height: 8, backgroundColor: s.color }} />
              <span className="text-secondary">{s.label}:</span>
              <span className="fw-bold text-dark">{val}</span>
              <span className="text-muted" style={{ fontSize: '11px' }}>
                ({pct}%)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
