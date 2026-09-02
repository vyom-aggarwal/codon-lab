import { ErrorState } from '@/app/projects/error-state'
import { ScorecardView } from '@/components/scorecard/scorecard-view'
import { ApiError, fetchLabScorecard } from '@/lib/api'

export const dynamic = 'force-dynamic'

/**
 * The persistent scorecard, pooled across every target this lab has measured.
 *
 * Specification §5.9: "a persistent scorecard per predictor per target class
 * that accumulates across the lab's projects." Pooling happens over the
 * underlying predicted/measured pairs in the service, never by averaging
 * finished cards — see `domain/scorecard.accumulate`, which refuses that
 * shortcut by name and says why.
 */
export default async function LabScorecardPage() {
  let report
  try {
    report = await fetchLabScorecard()
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorState message={error.message} remedy={error.remedy} />
    }
    throw error
  }

  return <ScorecardView report={report} scope="All targets" />
}
