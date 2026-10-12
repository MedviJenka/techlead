import { useState } from 'react'
import { Link } from 'react-router'

import { useApproveReply, useRejectReply } from '../api/replies'
import type { ReplyDraft } from '../api/types'
import { inputClass, relativeTime } from './leadDisplay'
import { AiTag, Button, Icon } from './ui'

const OPEN = new Set<ReplyDraft['status']>(['pending_approval', 'awaiting_edit', 'failed'])

const DECIDED_VIA: Record<NonNullable<ReplyDraft['decided_via']>, string> = {
  whatsapp: 'via WhatsApp',
  dashboard: 'via dashboard',
  auto: 'automatically, no decision in time',
}

const clockTime = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

const STATUS_LABEL: Record<ReplyDraft['status'], string> = {
  pending_approval: 'Waiting for approval',
  awaiting_edit: 'Being edited on WhatsApp',
  sending: 'Sending…',
  sent: 'Sent',
  rejected: 'Rejected',
  failed: 'Not sent',
}

// An AI-drafted reply: approve it as is, edit then send, or reject. The owner may also decide on WhatsApp.
export function ReplyDraftCard({ businessId, draft, leadName }: { businessId: string; draft: ReplyDraft; leadName?: string }) {
  const approve = useApproveReply(businessId)
  const reject = useRejectReply(businessId)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(draft.message)
  const open = OPEN.has(draft.status)
  const busy = approve.isPending || reject.isPending
  const error = approve.error ?? reject.error

  return (
    <div className="space-y-3 p-4 text-[13px]">
      <div className="flex flex-wrap items-center gap-2">
        <AiTag label="AI draft" />
        {leadName && (
          <Link to={`/businesses/${businessId}/leads/${draft.lead_id}`} dir="auto" className="font-semibold hover:text-primary">
            {leadName}
          </Link>
        )}
        <span className={`font-mono text-[11px] ${draft.status === 'failed' ? 'text-danger' : 'text-ink-subtle'}`}>
          {STATUS_LABEL[draft.status]}
          {draft.status === 'sent' && draft.sent_at && ` ${relativeTime(draft.sent_at)}`}
          {draft.decided_via && draft.status !== 'awaiting_edit' && ` · ${DECIDED_VIA[draft.decided_via]}`}
          {draft.status === 'pending_approval' && draft.auto_send_at && ` · sends automatically at ${clockTime(draft.auto_send_at)}`}
          {draft.edited && ' · edited'}
        </span>
        <span className="ml-auto font-mono text-[11px] text-ink-subtle">{relativeTime(draft.created_at)}</span>
      </div>

      {editing ? (
        <textarea
          dir="auto"
          className={`${inputClass} h-auto w-full py-2`}
          rows={4}
          value={text}
          maxLength={4096}
          onChange={(event) => setText(event.target.value)}
          aria-label="Reply text"
          autoFocus
        />
      ) : (
        <p dir="auto" className={`rounded-sm bg-canvas p-3 whitespace-pre-wrap ${draft.status === 'rejected' ? 'text-ink-subtle line-through' : ''}`}>
          {draft.message}
        </p>
      )}
      {draft.objective && !editing && <p className="text-xs text-ink-subtle">Goal: {draft.objective}</p>}

      {draft.last_error && open && (
        <p className="flex items-start gap-1.5 text-xs text-warning">
          <Icon name="warning" className="text-base!" />
          {draft.last_error}
        </p>
      )}
      {error && <p className="text-xs text-danger">{error.message}</p>}

      {open && (
        <div className="flex flex-wrap gap-2">
          {editing ? (
            <>
              <Button
                size="sm"
                icon="send"
                disabled={busy || !text.trim()}
                onClick={() => approve.mutate({ draftId: draft.id, message: text.trim() }, { onSuccess: () => setEditing(false) })}
              >
                Send edited reply
              </Button>
              <Button size="sm" variant="subtle" disabled={busy} onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" icon={busy ? 'progress_activity' : 'send'} disabled={busy} onClick={() => approve.mutate({ draftId: draft.id })}>
                {draft.status === 'failed' ? 'Try again' : 'Approve & send'}
              </Button>
              <Button size="sm" variant="ghost" icon="edit" disabled={busy} onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button size="sm" variant="danger" icon="close" disabled={busy} onClick={() => reject.mutate(draft.id)}>
                Reject
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
