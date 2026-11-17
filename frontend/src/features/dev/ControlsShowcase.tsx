import { Plus, Settings2, Trash2 } from 'lucide-react'
import { useState } from 'react'

import {
  Button,
  Card,
  CardContent,
  Checkbox,
  Field,
  Input,
  RadioGroup,
  SearchInput,
  Select,
  Textarea,
  Tooltip,
  type ButtonVariant,
} from '@/components/ui'
import { toast } from '@/stores/toast.store'

import { Example, ShowcaseSection } from './showcase-helpers'

const VARIANTS: ButtonVariant[] = ['primary', 'secondary', 'outline', 'ghost', 'destructive']

const REGIONS = [
  { value: 'us-east-1', label: 'US East (N. Virginia)' },
  { value: 'eu-west-1', label: 'Europe (Ireland)' },
  { value: 'ap-south-1', label: 'Asia Pacific (Mumbai)' },
  { value: 'cn-north-1', label: 'China (Beijing) — unavailable', disabled: true },
]

const SERVICES = ['Amazon ECS', 'Amazon EKS', 'AWS Lambda', 'Amazon Aurora', 'Amazon DynamoDB', 'Amazon ElastiCache', 'Amazon S3']

export function ButtonsShowcase() {
  const [lastClick, setLastClick] = useState('none yet')
  const [saving, setSaving] = useState(false)

  const save = () => {
    setSaving(true)
    window.setTimeout(() => {
      setSaving(false)
      toast({ tone: 'success', title: 'Saved', description: 'The loading button finished its action.' })
    }, 1500)
  }

  return (
    <ShowcaseSection id="buttons" title="Buttons" description="Variants, sizes and states. Every button here runs its callback.">
      <Card>
        <CardContent className="space-y-6 py-5">
          <Example label="Variants">
            {VARIANTS.map((variant) => (
              <Button key={variant} variant={variant} onClick={() => setLastClick(variant)}>
                {variant[0].toUpperCase() + variant.slice(1)}
              </Button>
            ))}
          </Example>
          <Example label="Sizes">
            <Button size="sm">Small</Button>
            <Button size="md">Medium</Button>
            <Button size="lg">Large</Button>
            <Tooltip content="Settings">
              <Button size="icon-sm" variant="outline" aria-label="Settings" onClick={() => setLastClick('icon-sm')}>
                <Settings2 className="size-4" aria-hidden="true" />
              </Button>
            </Tooltip>
            <Tooltip content="Add service">
              <Button size="icon" variant="outline" aria-label="Add service" onClick={() => setLastClick('icon')}>
                <Plus className="size-4" aria-hidden="true" />
              </Button>
            </Tooltip>
          </Example>
          <Example label="States and icons">
            <Button loading={saving} onClick={save}>
              {saving ? 'Saving…' : 'Save (loads 1.5 s)'}
            </Button>
            <Button disabled>Disabled</Button>
            <Button variant="outline" disabled>
              Disabled outline
            </Button>
            <Button onClick={() => setLastClick('with icon')}>
              <Plus className="size-4" aria-hidden="true" />
              New Architecture
            </Button>
            <Button variant="destructive" onClick={() => setLastClick('delete')}>
              <Trash2 className="size-4" aria-hidden="true" />
              Delete
            </Button>
          </Example>
          <p className="text-meta text-muted-foreground" aria-live="polite">
            Last clicked: <span className="font-mono text-foreground">{lastClick}</span>
          </p>
        </CardContent>
      </Card>
    </ShowcaseSection>
  )
}

export function InputsShowcase() {
  const [name, setName] = useState('')
  const [nameTouched, setNameTouched] = useState(false)
  const [request, setRequest] = useState('')
  const [region, setRegion] = useState('')
  const [search, setSearch] = useState('')
  const [includeCost, setIncludeCost] = useState(true)
  const [accepted, setAccepted] = useState(false)
  const [priority, setPriority] = useState('balanced')

  const nameError = nameTouched && name.trim().length < 3 ? 'Enter at least 3 characters.' : undefined
  const matches = SERVICES.filter((service) => service.toLowerCase().includes(search.trim().toLowerCase()))

  return (
    <ShowcaseSection
      id="inputs"
      title="Inputs"
      description="Labels, helper text, validation errors, focus and disabled states. Values below update live."
    >
      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <Card>
          <CardContent className="grid gap-5 py-5 sm:grid-cols-2">
            <Field
              label="Project name"
              required
              hint="Lowercase letters, numbers and hyphens."
              error={nameError}
            >
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                onBlur={() => setNameTouched(true)}
                placeholder="e.g. checkout-service"
                autoComplete="off"
              />
            </Field>
            <Field label="Account ID" hint="Disabled field example." disabled>
              <Input defaultValue="123456789012" className="font-mono" />
            </Field>
            <Field label="Region" hint="Native select: arrow keys and type-ahead work.">
              <Select options={REGIONS} placeholder="Choose a region" value={region} onChange={(event) => setRegion(event.target.value)} />
            </Field>
            <Field label="Search services">
              <SearchInput value={search} onValueChange={setSearch} placeholder="Filter AWS services…" />
            </Field>
            <Field
              label="Workload description"
              hint="What the system does, expected users and traffic."
              className="sm:col-span-2"
            >
              <Textarea
                value={request}
                onChange={(event) => setRequest(event.target.value)}
                maxLength={4000}
                showCount
                placeholder="A video streaming platform for 50,000 concurrent viewers…"
              />
            </Field>
            <div className="space-y-3">
              <Checkbox
                label="Include cost estimate"
                description="Adds a monthly cost range to the report."
                checked={includeCost}
                onChange={(event) => setIncludeCost(event.target.checked)}
              />
              <Checkbox
                label="I understand estimates are educational"
                checked={accepted}
                onChange={(event) => setAccepted(event.target.checked)}
                error={accepted ? undefined : 'Required before generating.'}
              />
              <Checkbox label="Multi-region (coming later)" disabled />
            </div>
            <RadioGroup
              label="Optimization priority"
              value={priority}
              onValueChange={setPriority}
              hint="Arrow keys move between options."
              options={[
                { value: 'cost', label: 'Cost', description: 'Fewer, smaller services.' },
                { value: 'balanced', label: 'Balanced' },
                { value: 'performance', label: 'Performance', description: 'Lower latency, higher cost.' },
                { value: 'experimental', label: 'Experimental', disabled: true },
              ]}
            />
          </CardContent>
        </Card>

        <Card className="self-start">
          <CardContent className="space-y-3 py-5">
            <p className="text-card-title">Live values</p>
            <pre className="overflow-x-auto rounded-md bg-surface-muted p-3 font-mono text-meta">
              {JSON.stringify({ name, region, search, requestLength: request.length, includeCost, accepted, priority }, null, 2)}
            </pre>
            <p className="text-meta text-muted-foreground">
              Search matches: {matches.length ? matches.join(', ') : 'none'}
            </p>
          </CardContent>
        </Card>
      </div>
    </ShowcaseSection>
  )
}
