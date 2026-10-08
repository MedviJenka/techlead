import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { Business, BusinessCreate, HealthStatus, Me } from './types'

export const queryKeys = {
  health: ['health'] as const,
  me: ['me'] as const,
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

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: () => apiFetch<Me>('/me') })
}

export function useBusiness(id: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.business(id),
    queryFn: () => apiFetch<Business>(`/businesses/${id}`),
    ...options,
  })
}

export function useCreateBusiness() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: BusinessCreate) =>
      apiFetch<Business>('/businesses', { method: 'POST', body: JSON.stringify(data) }),
    onSuccess: (business) => {
      queryClient.setQueryData(queryKeys.business(business.id), business)
      return queryClient.invalidateQueries({ queryKey: queryKeys.me })
    },
  })
}
