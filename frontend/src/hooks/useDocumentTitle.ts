import { useEffect } from 'react'

/** Set the browser tab title to "<title> · ArchonAI". */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · ArchonAI`
  }, [title])
}
