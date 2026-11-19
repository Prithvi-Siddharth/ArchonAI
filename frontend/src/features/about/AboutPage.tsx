import { useSearchParams } from 'react-router'

import { PageHeader, Tabs } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import { AboutTab } from './AboutTab'
import { ABOUT_TABS, parseAboutTab } from './about-tabs'
import { HowToUseTab } from './HowToUseTab'
import { PrivacyTab } from './PrivacyTab'
import { TermsTab } from './TermsTab'

/** What ArchonAI is, its version, how to use it, and its privacy and terms. The tab is kept in `?tab=`. */
export function AboutPage() {
  useDocumentTitle('About')
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = parseAboutTab(searchParams.get('tab'))

  return (
    <div className="space-y-6">
      <PageHeader title="About ArchonAI" description="What it is, how to use it, and how your data is handled." />
      <div className="max-w-3xl">
        <Tabs
          label="About sections"
          items={ABOUT_TABS}
          value={tab}
          onValueChange={(id) =>
            setSearchParams(
              (params) => {
                const updated = new URLSearchParams(params)
                updated.set('tab', parseAboutTab(id))
                return updated
              },
              { replace: true },
            )
          }
        >
          {tab === 'about' ? <AboutTab /> : tab === 'how-to-use' ? <HowToUseTab /> : tab === 'privacy' ? <PrivacyTab /> : <TermsTab />}
        </Tabs>
      </div>
    </div>
  )
}
