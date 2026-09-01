import type { Metadata } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import type { ReactNode } from 'react'

import { AppFrame } from '@/components/app-frame'
import { QueryProvider } from '@/components/query-provider'
import { ToastProvider } from '@/components/ui/toast'
import { TooltipProvider } from '@/components/ui/tooltip'
import { fetchMeta } from '@/lib/api'

import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Codon Lab',
  description: 'Protein design copilot for wet-lab scientists.',
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  // If the API is unreachable the page below renders its own error state, which
  // explains the failure properly. Suppressing the banner here avoids claiming
  // anything about provider state we could not actually read.
  const demoMode = await fetchMeta()
    .then((meta) => meta.demo_mode)
    .catch(() => false)

  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body>
        <QueryProvider>
          <TooltipProvider delayDuration={300}>
            <ToastProvider>
              <AppFrame demoMode={demoMode}>{children}</AppFrame>
            </ToastProvider>
          </TooltipProvider>
        </QueryProvider>
      </body>
    </html>
  )
}
