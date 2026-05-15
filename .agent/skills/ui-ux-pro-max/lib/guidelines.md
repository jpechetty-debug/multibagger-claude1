# UI/UX Pro Max Guidelines

## 1. Accessibility (CRITICAL)
- `color-contrast` - Minimum 4.5:1 ratio for normal text (large text 3:1); Material Design
- `focus-states` - Visible focus rings on interactive elements (2–4px; Apple HIG, MD)
- `alt-text` - Descriptive alt text for meaningful images
- `aria-labels` - aria-label for icon-only buttons; accessibilityLabel in native (Apple HIG)
- `keyboard-nav` - Tab order matches visual order; full keyboard support (Apple HIG)
- `form-labels` - Use label with for attribute
- `skip-links` - Skip to main content for keyboard users
- `heading-hierarchy` - Sequential h1→h6, no level skip
- `color-not-only` - Don't convey info by color alone (add icon/text)
- `dynamic-type` - Support system text scaling; avoid truncation as text grows (Apple Dynamic Type, MD)
- `reduced-motion` - Respect prefers-reduced-motion; reduce/disable animations when requested (Apple Reduced Motion API, MD)
- `voiceover-sr` - Meaningful accessibilityLabel/accessibilityHint; logical reading order for VoiceOver/screen readers (Apple HIG, MD)
- `escape-routes` - Provide cancel/back in modals and multi-step flows (Apple HIG)
- `keyboard-shortcuts` - Preserve system and a11y shortcuts; offer keyboard alternatives for drag-and-drop (Apple HIG)

## 2. Touch & Interaction (CRITICAL)
- `touch-target-size` - Min 44×44pt (Apple) / 48×48dp (Material); extend hit area beyond visual bounds if needed
- `touch-spacing` - Minimum 8px/8dp gap between touch targets (Apple HIG, MD)
- `hover-vs-tap` - Use click/tap for primary interactions; don't rely on hover alone
- `loading-buttons` - Disable button during async operations; show spinner or progress
- `error-feedback` - Clear error messages near problem
- `cursor-pointer` - Add cursor-pointer to clickable elements (Web)
- `gesture-conflicts` - Avoid horizontal swipe on main content; prefer vertical scroll
- `tap-delay` - Use touch-action: manipulation to reduce 300ms delay (Web)
- `standard-gestures` - Use platform standard gestures consistently; don't redefine (e.g. swipe-back, pinch-zoom) (Apple HIG)
- `system-gestures` - Don't block system gestures (Control Center, back swipe, etc.) (Apple HIG)
- `press-feedback` - Visual feedback on press (ripple/highlight; MD state layers)
- `haptic-feedback` - Use haptic for confirmations and important actions; avoid overuse (Apple HIG)
- `gesture-alternative` - Don't rely on gesture-only interactions; always provide visible controls for critical actions
- `safe-area-awareness` - Keep primary touch targets away from notch, Dynamic Island, gesture bar and screen edges
- `no-precision-required` - Avoid requiring pixel-perfect taps on small icons or thin edges
- `swipe-clarity` - Swipe actions must show clear affordance or hint (chevron, label, tutorial)
- `drag-threshold` - Use a movement threshold before starting drag to avoid accidental drags

## 3. Performance (HIGH)
- `image-optimization` - Use WebP/AVIF, responsive images (srcset/sizes), lazy load non-critical assets
- `image-dimension` - Declare width/height or use aspect-ratio to prevent layout shift (Core Web Vitals: CLS)
- `font-loading` - Use font-display: swap/optional to avoid invisible text (FOIT); reserve space to reduce layout shift (MD)
- `font-preload` - Preload only critical fonts; avoid overusing preload on every variant
- `critical-css` - Prioritize above-the-fold CSS (inline critical CSS or early-loaded stylesheet)
- `lazy-loading` - Lazy load non-hero components via dynamic import / route-level splitting
- `bundle-splitting` - Split code by route/feature (React Suspense / Next.js dynamic) to reduce initial load and TTI
- `third-party-scripts` - Load third-party scripts async/defer; audit and remove unnecessary ones (MD)
- `reduce-reflows` - Avoid frequent layout reads/writes; batch DOM reads then writes

## 4. Style Selection (HIGH)
- `product-matching` - Style must match product type (e.g., Glassmorphism for Fintech, Organic for Agri-tech)
- `visual-consistency` - Maintain consistent radius, borders, and shadows across all components
- `icon-system` - Use a single consistent SVG icon set (e.g., Lucide, Heroicons); avoid mixed styles
- `no-emoji-icons` - Never use emojis as functional icons; use SVGs for professional look
- `depth-hierarchy` - Use z-index and shadows to convey information hierarchy (Surface → Elevated → Floating)

## 5. Layout & Responsive (HIGH)
- `mobile-first` - Design for 375px first, then scale up to 768px, 1024px, 1440px
- `viewport-meta` - Use standard responsive viewport tags; don't disable user scaling
- `no-horizontal-scroll` - Prevent horizontal scroll on main body content
- `fluid-containers` - Use max-width and margin: auto; avoid fixed pixel widths for main layout
- `grid-consistency` - Use a consistent 4px/8px grid system for spacing and gutters

## 6. Typography & Color (MEDIUM)
- `base-size` - Minimum 16px/16pt for body text on mobile/web
- `line-height` - Use 1.5 for body text, 1.2 for headings
- `color-tokens` - Use semantic color variables (primary, background, error) instead of raw hex
- `contrast-check` - Verify contrast for both primary and secondary text (4.5:1 / 3:1)
- `font-limit` - Use max 2 font families; limit font weight variants to reduce load

## 7. Animation (MEDIUM)
- `duration` - UI transitions 150-300ms; larger reveals 400-600ms
- `easing` - Use ease-out or spring physics; avoid linear animation for UI elements
- `meaningful-motion` - Animation should guide the user (e.g., modal slides from its trigger)
- `exit-faster` - Elements should leave the screen faster than they enter
- `reduced-motion` - Respect system reduced motion settings

## 8. Forms & Feedback (MEDIUM)
- `visible-labels` - Always use visible labels; don't rely on placeholders alone
- `error-proximity` - Show error messages immediately adjacent to the problematic field
- `progressive-disclosure` - Hide complex options until needed to reduce cognitive load
- `focus-management` - Manage focus in modals and forms; return focus to trigger on close

## 9. Navigation Patterns (HIGH)
- `predictable-back` - Back button must always go to the previous logical screen
- `nav-limit` - Limit bottom navigation to 3-5 primary destinations
- `deep-linking` - Support URL-based navigation for all primary screens
- `active-states` - Clearly indicate the current active tab or page in the navigation

## 10. Charts & Data (LOW)
- `accessible-viz` - Use patterns or text in addition to color to distinguish data series
- `interactive-tooltips` - Provide clear tooltips for data points on hover/tap
- `chart-legends` - Always include a clear legend if multiple data series are present
- `responsive-charts` - Ensure charts adapt their density/detail based on screen size

## Final Pre-Delivery Checklist
- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons come from a consistent icon family and style
- [ ] Official brand assets are used with correct proportions and clear space
- [ ] Pressed-state visuals do not shift layout bounds or cause jitter
- [ ] Semantic theme tokens are used consistently (no ad-hoc per-screen hardcoded colors)
- [ ] All tappable elements provide clear pressed feedback (ripple/opacity/elevation)
- [ ] Touch targets meet minimum size (>=44x44pt iOS, >=48x48dp Android)
- [ ] Micro-interaction timing stays in the 150-300ms range with native-feeling easing
- [ ] Disabled states are visually clear and non-interactive
- [ ] Screen reader focus order matches visual order, and interactive labels are descriptive
- [ ] Gesture regions avoid nested/conflicting interactions (tap/drag/back-swipe conflicts)
- [ ] Primary text contrast >=4.5:1 in both light and dark mode
- [ ] Secondary text contrast >=3:1 in both light and dark mode
- [ ] Dividers/borders and interaction states are distinguishable in both modes
- [ ] Modal/drawer scrim opacity is strong enough to preserve foreground legibility (typically 40-60% black)
- [ ] Both themes are tested before delivery (not inferred from a single theme)
- [ ] Safe areas are respected for headers, tab bars, and bottom CTA bars
- [ ] Scroll content is not hidden behind fixed/sticky bars
- [ ] Verified on small phone, large phone, and tablet (portrait + landscape)
- [ ] Horizontal insets/gutters adapt correctly by device size and orientation
- [ ] 4/8dp spacing rhythm is maintained across component, section, and page levels
- [ ] Long-form text measure remains readable on larger devices (no edge-to-edge paragraphs)
- [ ] All meaningful images/icons have accessibility labels
- [ ] Form fields have labels, hints, and clear error messages
- [ ] Color is not the only indicator
- [ ] Reduced motion and dynamic text size are supported without layout breakage
- [ ] Accessibility traits/roles/states (selected, disabled, expanded) are announced correctly
