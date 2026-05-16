import { LayoutGrid, Menu, Activity } from 'lucide-react'

interface FloorDockProps {
  activeTab: string
  onTabChange: (tab: string) => void
}

export function FloorDock({ activeTab, onTabChange }: FloorDockProps) {
  const tabs = [
    { name: 'Signals', icon: LayoutGrid },
    { name: 'Swing Trades', icon: Activity },
  ]

  return (
    <footer className="floor-dock backdrop-blur-3xl border border-white/5 group hover:border-brand-primary/30 transition-all">
      <div className="flex items-center gap-1 p-1 bg-white/5 rounded-xl">
        {tabs.map(tab => (
          <button
            key={tab.name}
            onClick={() => onTabChange(tab.name)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-300 relative ${activeTab === tab.name ? 'bg-brand-primary text-brand-bg font-bold shadow-lg shadow-brand-primary/20' : 'text-brand-text-dim hover:text-brand-text'}`}
          >
            <tab.icon className={`w-4 h-4 ${activeTab === tab.name ? 'animate-pulse' : ''}`} />
            <span className="text-[10px] font-mono uppercase tracking-widest leading-none hidden md:inline">{tab.name}</span>
            {activeTab === tab.name && (
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-brand-bg rounded-full border-2 border-brand-primary" />
            )}
          </button>
        ))}
      </div>
      <div className="w-[1px] h-8 bg-white/10 mx-2" />
      <button 
        aria-label="Open Menu"
        className="w-10 h-10 flex items-center justify-center rounded-xl bg-brand-card/50 text-brand-text-dim hover:text-brand-primary hover:border-brand-primary/30 border border-transparent transition-all"
      >
        <Menu className="w-5 h-5" />
      </button>
    </footer>
  )
}
