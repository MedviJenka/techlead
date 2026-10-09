import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import { businessPath, useLeadData } from './leads'
import type { Preset, ReplyDraft, WhatsAppConnection, WhatsAppStatus } from './types'

export const usePresets = () =>
  useQuery({ queryKey: ['presets'], queryFn: () => apiFetch<Preset[]>('/businesses/presets'), staleTime: Infinity })

export const usePendingReplies = (id: string) => useLeadData<ReplyDraft[]>(id, '/replies')
export const useLeadReplies = (id: string, leadId: string) => useLeadData<ReplyDraft[]>(id, `/leads/${leadId}/replies`)
export const useWhatsApp = (id: string) => useLeadData<WhatsAppStatus>(id, '/whatsapp')

// Every decision refreshes the business's data: the queue, the lead's timeline and the dashboard metrics.
function useBusinessMutation<T, P>(id: string, request: (payload: P) => Promise<T>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSettled: () => client.invalidateQueries({ queryKey: ['businesses', id] }),
  })
}

export const useApproveReply = (id: string) =>
  useBusinessMutation(id, ({ draftId, message }: { draftId: string; message?: string }) =>
    apiFetch<ReplyDraft>(`${businessPath(id)}/replies/${draftId}/approve`, {
      method: 'POST',
      body: JSON.stringify(message ? { message } : {}),
    }),
  )

export const useRejectReply = (id: string) =>
  useBusinessMutation(id, (draftId: string) =>
    apiFetch<ReplyDraft>(`${businessPath(id)}/replies/${draftId}/reject`, { method: 'POST' }),
  )

export const useConnectWhatsApp = (id: string) =>
  useBusinessMutation(id, (connection: WhatsAppConnection) =>
    apiFetch(`${businessPath(id)}/whatsapp`, { method: 'PUT', body: JSON.stringify(connection) }),
  )

export const useDisconnectWhatsApp = (id: string) =>
  useBusinessMutation(id, () => apiFetch(`${businessPath(id)}/whatsapp`, { method: 'DELETE' }))
