'use client'

import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/cn'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
  /** Shown when the option is unavailable, so a greyed row explains itself. */
  disabledReason?: string
}

export interface SelectProps {
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  'aria-label'?: string
  className?: string
}

export function Select({
  value,
  defaultValue,
  onValueChange,
  options,
  placeholder = 'Select',
  disabled = false,
  className,
  ...props
}: SelectProps) {
  // Radix declares these as `value?: string` rather than `string | undefined`, so
  // under exactOptionalPropertyTypes they must be omitted rather than passed as
  // undefined. Spreading conditionally is what keeps that flag on — it is worth
  // holding onto in a codebase where "absent" and "unmeasured" are different facts.
  const controlled = {
    ...(value === undefined ? {} : { value }),
    ...(defaultValue === undefined ? {} : { defaultValue }),
    ...(onValueChange === undefined ? {} : { onValueChange }),
  }

  return (
    <SelectPrimitive.Root {...controlled} disabled={disabled}>
      <SelectPrimitive.Trigger
        aria-label={props['aria-label']}
        className={cn(
          'h-control rounded-control inline-flex items-center justify-between gap-2 border',
          'bg-surface text-13 text-text px-2',
          'hover:border-border-strong',
          'disabled:bg-surface-sunk disabled:text-text-faint disabled:pointer-events-none',
          'duration-fast ease-out-quint transition-[border-color]',
          'data-[placeholder]:text-text-faint',
          className,
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown aria-hidden="true" className="text-text-faint size-4" strokeWidth={1.5} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>

      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className={cn(
            'z-50 min-w-[var(--radix-select-trigger-width)] overflow-hidden',
            'rounded-dialog border-border bg-surface shadow-popover border',
            'animate-[layer-in_var(--duration-fast)_var(--ease-out-quint)]',
          )}
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option) => (
              <SelectItem key={option.value} option={option} />
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}

function SelectItem({ option }: { option: SelectOption }): ReactNode {
  return (
    <SelectPrimitive.Item
      value={option.value}
      disabled={option.disabled ?? false}
      // A greyed-out option must say why it is unavailable. The UI greys out
      // objectives no provider supports, and silence there reads as a bug.
      {...(option.disabled && option.disabledReason ? { title: option.disabledReason } : {})}
      className={cn(
        'h-control-sm rounded-control relative flex cursor-default items-center',
        'text-13 text-text select-none pl-7 pr-2 outline-none',
        'data-[highlighted]:bg-surface-sunk',
        'data-[state=checked]:text-accent',
        'data-[disabled]:text-text-faint data-[disabled]:pointer-events-none',
      )}
    >
      <span className="absolute left-2 inline-flex items-center">
        <SelectPrimitive.ItemIndicator>
          <Check aria-hidden="true" className="size-4" strokeWidth={1.5} />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  )
}
