import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from './client'
import type {
  Activity,
  Dashboard,
  ImportResult,
  Lead,
  LeadDetail,
  Page,
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
