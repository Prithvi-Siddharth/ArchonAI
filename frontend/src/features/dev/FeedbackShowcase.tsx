import { Trash2 } from 'lucide-react'
import { useState } from 'react'

import { Button, Card, CardContent, ConfirmDialog, Field, Input, Modal } from '@/components/ui'
import { toast, type ToastTone } from '@/stores/toast.store'

import { Example, ShowcaseSection } from './showcase-helpers'

const TOASTS: { tone: ToastTone; label: string; title: string; description: string }[] = [
  { tone: 'info', label: 'Info', title: 'Job queued', description: 'Your architecture will start shortly.' },
  { tone: 'success', label: 'Success', title: 'Architecture ready', description: 'The critic approved the design.' },
  { tone: 'warning', label: 'Warning', title: 'Rate limited', description: 'Retrying in a moment.' },
  { tone: 'danger', label: 'Error', title: 'Generation failed', description: 'Please try again later.' },
]

export function FeedbackShowcase() {
  const [modalOpen, setModalOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [modalName, setModalName] = useState('')
  const [lastResult, setLastResult] = useState('none yet')

  const saveModal = () => {
    setModalOpen(false)
    setLastResult(`modal saved "${modalName}"`)
    toast({ tone: 'success', title: 'Renamed', description: `New name: ${modalName || '(empty)'}` })
  }

  const deleteArchitecture = async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
    setConfirmOpen(false)
    setLastResult('confirmed delete')
    toast({ tone: 'success', title: 'Architecture deleted' })
  }

  return (
    <ShowcaseSection
      id="feedback"
      title="Feedback"
      description="Modal, confirmation dialog and toasts. Dialogs keep focus inside, close with Escape and return focus to the button."
    >
      <Card>
        <CardContent className="space-y-6 py-5">
          <Example label="Dialogs">
            <Button
              variant="outline"
              onClick={() => {
                setModalName('checkout-service')
                setModalOpen(true)
              }}
            >
              Open modal
            </Button>
            <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
              <Trash2 className="size-4" aria-hidden="true" />
              Delete architecture
            </Button>
          </Example>
          <Example label="Toasts">
            {TOASTS.map(({ tone, label, title, description }) => (
              <Button key={tone} variant="outline" onClick={() => toast({ tone, title, description })}>
                {label}
              </Button>
            ))}
            <Button
              variant="ghost"
              onClick={() => toast({ title: 'Stays until dismissed', description: 'duration: 0', duration: 0 })}
            >
              Persistent
            </Button>
          </Example>
          <p className="text-meta text-muted-foreground" aria-live="polite">
            Last dialog result: <span className="font-mono text-foreground">{lastResult}</span>
          </p>
        </CardContent>
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false)
          setLastResult('modal dismissed')
        }}
        title="Rename architecture"
        description="The name appears in the dashboard and history."
        footer={
          <>
            <Button variant="outline" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={saveModal}>Save</Button>
          </>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault()
            saveModal()
          }}
        >
          <Field label="Name">
            <Input value={modalName} onChange={(event) => setModalName(event.target.value)} data-autofocus />
          </Field>
        </form>
      </Modal>

      <ConfirmDialog
        open={confirmOpen}
        onCancel={() => {
          setConfirmOpen(false)
          setLastResult('confirm cancelled')
        }}
        onConfirm={deleteArchitecture}
        title="Delete this architecture?"
        description="The design, its report and its cost estimate will be removed. This can't be undone."
        confirmLabel="Delete"
        tone="destructive"
      />
    </ShowcaseSection>
  )
}
