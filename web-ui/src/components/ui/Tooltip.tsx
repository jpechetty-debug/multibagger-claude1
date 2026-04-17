import { ReactNode, useState, useRef, useEffect } from 'react'

export function Tooltip({ children, content }: { children: ReactNode; content: ReactNode }) {
  const [show, setShow] = useState(false)
  const tooltipRef = useRef<HTMLDivElement>(null)

  // Quick effect to ensure it stays on screen if possible, but keeping it simple for Brutalist aesthetics
  return (
    <div 
      className="relative inline-block group"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      {children}
      {show && (
        <div 
          ref={tooltipRef}
          className="absolute z-50 w-64 p-3 bg-brand-card border-2 border-brand-accent text-xs shadow-[4px_4px_0_0_#00ffa3] pointer-events-none transform -translate-x-1/2 left-1/2 bottom-full mb-2"
        >
          {/* Triangle pointer */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-[6px] border-transparent border-t-brand-accent h-0 w-0" />
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-[4px] border-transparent border-t-brand-card h-0 w-0 mt-[-2px]" />
          
          {content}
        </div>
      )}
    </div>
  )
}
