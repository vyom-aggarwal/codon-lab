'use client'

import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ComponentPropsWithoutRef, ReactNode } from 'react'
import { forwardRef } from 'react'

import { cn } from '@/lib/cn'

/**
 * Dialogs are for interruptions that genuinely block. Anything the user needs to
 * reference while working belongs in the inspector instead — see DESIGN.md §2.
 */
export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

export const DialogContent = forwardRef<
  HTMLDivElement,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & {
    title: string
    description?: ReactNode
  }
>(function DialogContent({ className, title, description, children, ...props }, ref) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay
        className={cn(
          'bg-text/20 fixed inset-0 z-50',
          'animate-[overlay-in_var(--duration-base)_var(--ease-out-quint)]',
        )}
      />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          'fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2',
          'rounded-dialog border-border bg-surface border',
          'shadow-dialog',
          'animate-[layer-in_var(--duration-base)_var(--ease-out-quint)]',
          className,
        )}
        {...props}
      >
        <div className="border-border flex items-start justify-between gap-4 border-b p-4">
          <div className="space-y-1">
            <DialogPrimitive.Title className="text-15 font-strong">{title}</DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="text-12 text-text-muted">
                {description}
              </DialogPrimitive.Description>
            ) : null}
          </div>
          <DialogPrimitive.Close
            aria-label="Close"
            className={cn(
              'rounded-control inline-flex size-6 shrink-0 items-center justify-center',
              'text-text-muted hover:bg-surface-sunk hover:text-text',
            )}
          >
            <X aria-hidden="true" className="size-4" strokeWidth={1.5} />
          </DialogPrimitive.Close>
        </div>
        <div className="p-4">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
})

export function DialogFooter({ className, ...props }: { className?: string; children: ReactNode }) {
  return <div className={cn('flex justify-end gap-2 pt-4', className)} {...props} />
}
