'use client'

import type { Route } from 'next'
import { Plus } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'

import { createProjectAction } from '@/app/actions'
import { InlineError } from '@/components/inline-error'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/ui/toast'

export function NewProjectDialog() {
  const router = useRouter()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<{ message: string; remedy: string } | null>(null)
  const [name, setName] = useState('')
  const [organism, setOrganism] = useState('')
  const [objective, setObjective] = useState('')

  function submit() {
    setError(null)
    startTransition(async () => {
      const result = await createProjectAction({ name, organism, objective })
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      // The button says "Create project"; the toast says "Project created".
      toast({ title: 'Project created' })
      setOpen(false)
      setName('')
      setOrganism('')
      setObjective('')
      router.push(`/projects/${result.data.id}` as Route)
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setError(null)
      }}
    >
      <DialogTrigger asChild>
        <Button variant="primary" size="sm">
          <Plus aria-hidden="true" strokeWidth={1.5} />
          New project
        </Button>
      </DialogTrigger>
      <DialogContent
        title="New project"
        description="A project holds one target and the runs made against it."
      >
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            submit()
          }}
        >
          <Field label="Name" hint="Shown in the projects table.">
            <Input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="TEM-1 thermostability"
              aria-label="Project name"
            />
          </Field>
          <Field label="Organism" hint="Optional.">
            <Input
              value={organism}
              onChange={(event) => setOrganism(event.target.value)}
              placeholder="Escherichia coli"
              aria-label="Organism"
            />
          </Field>
          <Field label="Objective" hint="Plain English. The parsed objective comes later.">
            <Input
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              placeholder="Raise the melting temperature without losing activity."
              aria-label="Objective"
            />
          </Field>

          {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}

          <DialogFooter>
            <Button type="button" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={pending || !name.trim()}>
              {pending ? 'Creating…' : 'Create project'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="block space-y-1">
      <span className="text-11 text-text-muted block font-medium uppercase tracking-wide">
        {label}
      </span>
      {children}
      {hint ? <span className="text-12 text-text-faint block">{hint}</span> : null}
    </label>
  )
}
