---
name: ui-ux-pro-max
description: "UI/UX design intelligence for web and mobile. Includes 50+ styles, 161 color palettes, 57 font pairings, 161 product types, 99 UX guidelines, and 25 chart types across 10 stacks (React, Next.js, Vue, Svelte, SwiftUI, React Native, Flutter, Tailwind, shadcn/ui, and HTML/CSS). Actions: plan, build, create, design, implement, review, fix, improve, optimize, enhance, refactor, and check UI/UX code. Projects: website, landing page, dashboard, admin panel, e-commerce, SaaS, portfolio, blog, and mobile app. Elements: button, modal, navbar, sidebar, card, table, form, and chart. Styles: glassmorphism, claymorphism, minimalism, brutalism, neumorphism, bento grid, dark mode, responsive, skeuomorphism, and flat design. Topics: color systems, accessibility, animation, layout, typography, font pairing, spacing, interaction states, shadow, and gradient. Integrations: shadcn/ui MCP for component search and examples."
---

UI/UX intelligence for hierarchical design generation and verification.

### Activation Rules
- **Must Use**: New pages, UI components, color/typography choices, UX reviews, navigation/animations.
- **Recommended**: Professional polish, usability feedback, cross-platform alignment.
- **Skip**: Pure backend, DB design, non-visual automation.

### Quick Start
1. **Analyze**: Identify product type, audience, and style.
2. **Design System (MASTER.md)**:
   ```bash
   python scripts/search.py "<query>" --design-system --persist -p "ProjectName"
   ```
3. **Deep Dive**:
   ```bash
   python scripts/search.py "<keyword>" --domain <domain>  # (ux, color, style, chart)
   ```
4. **Stack Guidelines**:
   ```bash
   python scripts/search.py "<keyword>" --stack react-native
   ```

### Hierarchical Retrieval
When building a page, check `design-system/MASTER.md`. If `design-system/pages/[page].md` exists, its rules **override** Master.

### Reference
- [Full Guidelines & Checklist](file:///d:/Tradeidesa/Multibagger-claude/.agent/skills/ui-ux-pro-max/lib/guidelines.md)
- [Available Domains & Usage](file:///d:/Tradeidesa/Multibagger-claude/.agent/skills/ui-ux-pro-max/lib/usage.md)
