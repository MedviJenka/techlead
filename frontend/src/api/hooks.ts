import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { Business, BusinessCreate, HealthStatus } from './types'

export const queryKeys = {
  health: ['health'] as const,
  business: (id: string) => ['businesses', id] as const,
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => apiFetch<HealthStatus>('/health'),
    refetchInterval: 30_000,
    retry: false,
  })
}

export function useBusiness(id: string) {
  return useQuery({
    queryKey: queryKeys.business(id),
    queryFn: () => apiFetch<Business>(`/businesses/${id}`),
  })
}

export function useCreateBusiness() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: BusinessCreate) =>
      apiFetch<Business>('/businesses', { method: 'POST', body: JSON.stringify(data) }),
    onSuccess: (business) => queryClient.setQueryData(queryKeys.business(business.id), business),
  })
}
