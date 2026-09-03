import { AlertTriangle } from 'lucide-react'

/**
 * An error states what failed, what it means, and the one action that fixes it.
 * "Oops! Something went wrong" is banned — it tells a busy scientist nothing.
 */
export function ErrorState({ message, remedy }: { message: string; remedy: string }) {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="rounded-panel border-border bg-surface max-w-md space-y-2 border p-4">
        <div className="flex items-center gap-2">
          <AlertTriangle aria-hidden="true" className="text-warn size-4" strokeWidth={1.5} />
          <p className="text-13 text-text font-medium">Projects could not be loaded</p>
        </div>
        <p className="text-12 text-text-muted">{message}</p>
        <p className="text-12 text-text-muted">{remedy}</p>
      </div>
    </div>
  )
}
