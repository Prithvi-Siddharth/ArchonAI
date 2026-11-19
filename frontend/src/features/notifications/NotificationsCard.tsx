import { Bell, BellOff, BellRing } from 'lucide-react'
import { useState } from 'react'

import { Badge, Button, Card, CardHeader } from '@/components/ui'
import { toast } from '@/stores/toast.store'

import { desktopSupport, enableDesktop, permission, showDesktop, useDesktopPref } from './desktop'

/** Choose how you are told when a job finishes. In-app pop-ups are always on; desktop ones are opt-in. */
export function NotificationsCard() {
  const enabled = useDesktopPref((state) => state.enabled)
  const setEnabled = useDesktopPref((state) => state.setEnabled)
  const [current, setCurrent] = useState(permission())
  const [asking, setAsking] = useState(false)
  const support = desktopSupport()

  const turnOn = async () => {
    setAsking(true)
    try {
      setCurrent(await enableDesktop())
    } finally {
      setAsking(false)
    }
  }

  const sendTest = () => {
    toast({ tone: 'info', title: 'Test notification', description: 'This is how a finished job will look.' })
    showDesktop('Test notification', 'Desktop notifications are working.', 'archonai-test', () => undefined)
  }

  let desktop
  if (support === 'unsupported') {
    desktop = <p className="text-muted-foreground">This browser can’t show desktop notifications.</p>
  } else if (support === 'insecure') {
    desktop = <p className="text-muted-foreground">Desktop notifications only work on localhost or an HTTPS address.</p>
  } else if (current === 'denied') {
    desktop = (
      <p className="text-muted-foreground">
        Notifications are blocked for this site in your browser. Allow them in the site settings (the icon at the left of the address bar), then reload this page.
      </p>
    )
  } else if (current === 'granted' && enabled) {
    desktop = (
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone="success">
          <BellRing className="size-3.5" aria-hidden="true" />
          On
        </Badge>
        <Button variant="outline" size="sm" onClick={sendTest}>
          Send a test
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setEnabled(false)}>
          Turn off
        </Button>
      </div>
    )
  } else if (current === 'granted') {
    desktop = (
      <div className="flex flex-wrap items-center gap-3">
        <Badge>
          <BellOff className="size-3.5" aria-hidden="true" />
          Off
        </Badge>
        <Button variant="outline" size="sm" onClick={() => setEnabled(true)}>
          Turn on
        </Button>
      </div>
    )
  } else {
    desktop = (
      <div className="space-y-2">
        <Button onClick={() => void turnOn()} loading={asking}>
          {!asking && <Bell className="size-4" aria-hidden="true" />}
          Enable desktop notifications
        </Button>
        <p className="text-meta text-muted-foreground">Your browser will ask for permission.</p>
      </div>
    )
  }

  return (
    <Card>
      <CardHeader title="Notifications" description="Get told when a job you submitted finishes, succeeded or failed." />
      <div className="space-y-5 px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-label">In-app pop-up</p>
            <p className="text-meta text-muted-foreground">Shown wherever you are in ArchonAI, with a button to open the job.</p>
          </div>
          <Badge tone="success">Always on</Badge>
        </div>
        <div className="space-y-2 border-t border-border pt-5" data-testid="desktop-notifications">
          <div>
            <p className="text-label">Desktop notification</p>
            <p className="text-meta text-muted-foreground">Shown when this tab is in the background. Clicking it opens the job.</p>
          </div>
          {desktop}
        </div>
        <p className="text-meta text-muted-foreground">
          Notifications show the start of your request and only work while ArchonAI is open in a browser tab. Jobs that finish while it is closed are in Architecture History.
        </p>
      </div>
    </Card>
  )
}
