/** The About page's sections, in display order. The id is the `?tab=` value. */
export const ABOUT_TABS = [
  { id: 'about', label: 'About' },
  { id: 'how-to-use', label: 'How to use' },
  { id: 'privacy', label: 'Privacy' },
  { id: 'terms', label: 'Terms' },
] as const

export type AboutTab = (typeof ABOUT_TABS)[number]['id']

/** The tab named by a `?tab=` value; anything missing or unknown falls back to About. */
export function parseAboutTab(value: string | null): AboutTab {
  return ABOUT_TABS.find((tab) => tab.id === value)?.id ?? 'about'
}

export const APP_VERSION: string = __APP_VERSION__

/** When the privacy and terms text was last reviewed. Update it whenever either changes. */
export const POLICY_UPDATED = '19 November 2026'
