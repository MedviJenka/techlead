import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { apiFetch } from './client'
import type {
  Activity,
  Dashboard,
  ImportResult,
  Lead,
  AnalysisJob,
  LeadAnalysisState,
  LeadDetail,
  Page,
  RescoreResult,
  ScoreBreakdown,
} from './types'

export const businessPath = (id: string) => `/businesses/${id}`
export function useLeadData<T>(businessId: string, suffix: string) {
  return useQuery({
    queryKey: ['businesses', businessId, suffix],
    queryFn: () => apiFetch<T>(businessPath(businessId) + suffix),
  })
}
export const useDashboard = (id: string) =>
  useLeadData<Dashboard>(id, '/dashboard')
export const useLeads = (id: string, query: string) =>
  useLeadData<Page<Lead>>(id, `/leads?${query}`)
export const useLead = (id: string, leadId: string) =>
  useLeadData<LeadDetail>(id, `/leads/${leadId}`)
export const useScore = (id: string, leadId: string) =>
  useLeadData<ScoreBreakdown>(id, `/leads/${leadId}/score`)
export const useActivities = (id: string, leadId: string, offset: number) =>
  useLeadData<Page<Activity>>(
    id,
    `/leads/${leadId}/activities?offset=${offset}`,
  )

export function useLeadMutation<T>(
  id: string,
  suffix: string,
  method = 'POST',
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: unknown) =>
      apiFetch<T>(businessPath(id) + suffix, {
        method,
        body: JSON.stringify(payload),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['businesses', id] }),
  })
}
export const useImport = (id: string) =>
  useLeadMutation<ImportResult>(id, '/leads/import')
export const useRescore = (id: string) =>
  useLeadMutation<RescoreResult>(id, '/leads/rescore')
export const useAnalyze = (id: string, leadId: string) =>
  useLeadMutation<AnalysisJob>(id, `/leads/${leadId}/analyze`)

const isOpen = (state: LeadAnalysisState | undefined) =>
  state?.job?.status === 'pending' || state?.job?.status === 'running'

// Polls while a job is queued or running; the lead and its timeline refresh when it finishes.
export function useAnalysisState(id: string, leadId: string) {
  const client = useQueryClient()
  const wasOpen = useRef(false)
  const query = useQuery({
    queryKey: ['businesses', id, `/leads/${leadId}/analysis`],
    queryFn: () => apiFetch<LeadAnalysisState>(`${businessPath(id)}/leads/${leadId}/analysis`),
    refetchInterval: (q) => (isOpen(q.state.data) ? 3000 : false),
  })
  const open = isOpen(query.data)
  useEffect(() => {
    if (wasOpen.current && !open) void client.invalidateQueries({ queryKey: ['businesses', id] })
    wasOpen.current = open
  }, [client, id, open])
  return query
}
