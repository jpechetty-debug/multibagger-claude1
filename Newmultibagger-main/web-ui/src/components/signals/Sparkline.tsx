interface SparklineProps {
  points: number[]
  className?: string
}

/**
 * Minimal trend line for a card. Renders nothing until there are at
 * least two points, so callers don't need to gate on loading state
 * themselves — an empty/loading sparkline just collapses to 0 height.
 */
export function Sparkline({ points, className }: SparklineProps) {
  if (points.length < 2) {
    return <div className="h-6" aria-hidden="true" />
  }

  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = max - min || 1
  const width = 100
  const height = 24
  const step = width / (points.length - 1)

  const coords = points.map((value, index) => {
    const x = index * step
    const y = height - ((value - min) / range) * height
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })

  const isUp = points[points.length - 1] >= points[0]
  const strokeColor = isUp ? 'rgb(16 185 129)' : 'rgb(239 68 68)' // brand-emerald / brand-rose

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={`h-6 w-full ${className ?? ''}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={isUp ? 'Price trending up' : 'Price trending down'}
    >
      <polyline
        points={coords.join(' ')}
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
