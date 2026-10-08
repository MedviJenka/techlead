import { createClient, type Session } from '@supabase/supabase-js'
import { useEffect, useState } from 'react'

// Used only for sign-in: the publishable key has no access to the tables (db/003_lock_down_data_api.sql).
// All data goes through the backend, which verifies the session's access token.
export const supabase = createClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY, {
  auth: { flowType: 'pkce' },
})

export function signInWithGoogle() {
  // Google returns here; supabase-js finishes the sign-in from the URL on load.
  return supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.href } })
}

export async function accessToken(): Promise<string | undefined> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token
}

/** The current session: `undefined` while loading, `null` when signed out. */
export function useSession(): Session | null | undefined {
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next))
    return () => data.subscription.unsubscribe()
  }, [])
  return session
}
