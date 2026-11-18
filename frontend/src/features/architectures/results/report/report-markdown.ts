import type { FinalReport } from '@/types/api'

import { REPORT_SECTIONS, reportList, reportText } from './report-content'

export const REPORT_TITLE = 'ArchonAI architecture report'
export const NOT_PROVIDED = '_Not provided._'
export const NONE_LISTED = '_None listed._'

/**
 * Escape one line of backend text so Markdown renders it exactly as written: characters that
 * would start emphasis, code, links, HTML, strikethrough or entities are backslash-escaped,
 * and so is anything at the line start that would become a heading, quote, list or rule.
 */
export function escapeMarkdownLine(line: string): string {
  const inline = line.replace(/[\\`*_[\]<~]/g, '\\$&').replace(/&(?=#?\w+;)/g, '\\&')
  if (/^(#{1,6}(\s|$)|>|[-+](\s|$)|=+\s*$|-+\s*$)/.test(inline)) return `\\${inline}`
  return inline.replace(/^(\d{1,9})([.)])(?=\s|$)/, '$1\\$2')
}

/**
 * Backend text as Markdown. Paragraph breaks (blank lines) stay paragraph breaks; single line
 * breaks become hard breaks (a trailing backslash), so no line is joined to the next.
 * `indent` prefixes continuation lines, for text inside a list item.
 */
function textToMarkdown(text: string, indent = ''): string {
  return text
    .split(/\n\s*\n/)
    .map((paragraph) =>
      paragraph
        .split('\n')
        .map((line) => escapeMarkdownLine(line.trim()))
        .filter((line) => line !== '')
        .join(`\\\n${indent}`),
    )
    .filter((paragraph) => paragraph !== '')
    .join(`\n\n${indent}`)
}

function listToMarkdown(items: string[], ordered: boolean): string {
  return items
    .map((item, index) => {
      const marker = ordered ? `${index + 1}. ` : '- '
      return marker + textToMarkdown(item, ' '.repeat(marker.length))
    })
    .join('\n')
}

/**
 * The whole report as a Markdown document, built in the browser from the result already loaded.
 * Every section appears in the backend's order with its original wording; nothing is added
 * except the title, the job ID and a marker for sections the report left empty.
 */
export function reportToMarkdown(report: FinalReport | undefined, jobId?: string): string {
  const parts = [`# ${REPORT_TITLE}`]
  const id = jobId?.replace(/\s+/g, ' ').trim()
  if (id) parts.push(`Job ID: ${escapeMarkdownLine(id)}`)
  for (const section of REPORT_SECTIONS) {
    let body: string
    if (section.kind === 'text') {
      const text = reportText(report, section.key)
      body = text ? textToMarkdown(text) : NOT_PROVIDED
    } else {
      const items = reportList(report, section.key)
      body = items.length ? listToMarkdown(items, section.key === 'final_recommendations') : NONE_LISTED
    }
    parts.push(`## ${section.title}`, body)
  }
  return `${parts.join('\n\n')}\n`
}

/** `archonai-report-{jobId}.md`, keeping only filename-safe characters; `archonai-report.md` without an ID. */
export function reportFilename(jobId?: string): string {
  const safe = (jobId ?? '').replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 100)
  return safe ? `archonai-report-${safe}.md` : 'archonai-report.md'
}
