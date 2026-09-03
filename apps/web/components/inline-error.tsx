import { AlertTriangle } from 'lucide-react'

/**
 * A failure states what went wrong and the one thing that fixes it. Used inline
 * beside the control that failed, so the remedy sits where the user is looking.
 */
export function InlineError({ message, remedy }: { message: string; remedy: string }) {
  return (
    <div role="alert" className="border-negative/30 bg-negative/8 rounded-control border p-2">
      <div className="flex items-start gap-1.5">
        <AlertTriangle aria-hidden="true" className="text-negative mt-px size-4 shrink-0" strokeWidth={1.5} />
        <div className="space-y-0.5">
          <p className="text-12 text-text">{message}</p>
          <p className="text-12 text-text-muted">{remedy}</p>
        </div>
      </div>
    </div>
  )
}
