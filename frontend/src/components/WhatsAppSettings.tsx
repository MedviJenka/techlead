import { type FormEvent, useState } from 'react'

import { useConnectWhatsApp, useDisconnectWhatsApp, useWhatsApp } from '../api/replies'
import type { WhatsAppStatus } from '../api/types'
import { inputClass, relativeTime } from './leadDisplay'
import { Button, Card, CardHeader, ErrorState, Icon, PulseDot, Skeleton } from './ui'

function ConnectForm({ businessId, status }: { businessId: string; status: WhatsAppStatus }) {
  const connect = useConnectWhatsApp(businessId)
  const current = status.connection
  const [phoneNumberId, setPhoneNumberId] = useState(current?.phone_number_id ?? '')
  const [displayPhone, setDisplayPhone] = useState(current?.display_phone ?? '')
  const [ownerPhone, setOwnerPhone] = useState(current?.owner_phone ?? '')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    connect.mutate({ phone_number_id: phoneNumberId.trim(), display_phone: displayPhone.trim() || null, owner_phone: ownerPhone.trim() })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted">
          Phone number ID
          <input className={`${inputClass} font-mono`} value={phoneNumberId} onChange={(e) => setPhoneNumberId(e.target.value)} placeholder="1098765432…" required inputMode="numeric" />
          <span className="font-normal text-ink-subtle">Meta app › WhatsApp › API Setup (not the phone number).</span>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted">
          Business WhatsApp number
          <input className={inputClass} value={displayPhone} onChange={(e) => setDisplayPhone(e.target.value)} placeholder="+972 50 000 0000" />
          <span className="font-normal text-ink-subtle">The number leads write to (optional, for display).</span>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted">
          Your WhatsApp (approvals)
          <input className={inputClass} value={ownerPhone} onChange={(e) => setOwnerPhone(e.target.value)} placeholder="+972 52 123 4567" required />
          <span className="font-normal text-ink-subtle">Drafted replies come here with Approve / Edit / Reject.</span>
        </label>
      </div>
      {connect.isError && <ErrorState message={connect.error.message} />}
      <div className="flex items-center gap-3">
        <Button type="submit" size="sm" icon={connect.isPending ? 'progress_activity' : 'link'} disabled={connect.isPending}>
          {current ? 'Save' : 'Connect WhatsApp'}
        </Button>
        {connect.isSuccess && <span className="text-xs text-success">Saved.</span>}
      </div>
    </form>
  )
}

export function WhatsAppSettings({ businessId }: { businessId: string }) {
  const status = useWhatsApp(businessId)
  const disconnect = useDisconnectWhatsApp(businessId)
  const data = status.data
  const webhookUrl = data ? `${window.location.origin}${data.webhook_path}` : ''

  return (
    <Card>
      <span id="whatsapp" className="block scroll-mt-20" />
      <CardHeader
        title="WhatsApp"
        icon="chat"
        action={
          data?.connection && (
            <span className="flex items-center gap-2 text-xs text-ink-muted">
              <PulseDot /> Connected · {relativeTime(data.connection.updated_at)}
            </span>
          )
        }
      />
      <div className="space-y-4 p-5 text-[13px]">
        <p className="text-ink-muted">
          New leads who write to your WhatsApp number get an AI-drafted first reply within a minute. It is sent to your own WhatsApp for approval; nothing
          reaches a lead until you approve it.
        </p>
        {status.isPending && <Skeleton className="h-24" />}
        {status.isError && <ErrorState message={status.error.message} onRetry={() => void status.refetch()} />}
        {data && !data.configured && (
          <p className="flex items-start gap-1.5 rounded-sm bg-canvas p-3 text-xs text-warning">
            <Icon name="warning" className="text-base!" />
            This server has no WhatsApp credentials yet (WHATSAPP_ACCESS_TOKEN, WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN). You can save your number now; messages
            flow once they are set.
          </p>
        )}
        {data && <ConnectForm businessId={businessId} status={data} key={data.connection?.updated_at ?? 'new'} />}
        {data && (
          <p className="text-xs text-ink-subtle">
            Webhook URL for the Meta app (subscribe to <span className="font-mono">messages</span>):{' '}
            <span className="font-mono break-all text-ink-muted">{webhookUrl}</span>
          </p>
        )}
        {data?.connection && (
          <Button size="sm" variant="danger" icon="link_off" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
            Disconnect
          </Button>
        )}
      </div>
    </Card>
  )
}
