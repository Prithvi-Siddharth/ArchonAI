/** Save `text` as a file, built entirely in the browser (no request). */
export function downloadText(filename: string, text: string, type: string): void {
  const blob = new Blob([text], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.append(link)
  link.click()
  link.remove()
  // Revoke after the click has been handled.
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

/** Save `data` as a pretty-printed JSON file, built entirely in the browser (no request). */
export function downloadJson(filename: string, data: unknown): void {
  downloadText(filename, `${JSON.stringify(data, null, 2)}\n`, 'application/json')
}
