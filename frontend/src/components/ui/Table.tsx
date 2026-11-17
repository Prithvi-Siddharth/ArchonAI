import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

import { Skeleton } from './Skeleton'

export interface Column<T> {
  key: string
  header: ReactNode
  cell: (row: T) => ReactNode
  align?: 'left' | 'right'
  /** Hide the column below this breakpoint. */
  hideBelow?: 'sm' | 'md' | 'lg'
  /** Take the remaining width; long text in it can truncate. */
  grow?: boolean
  className?: string
}

const HIDE_BELOW = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
} as const

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  getRowKey: (row: T) => string
  /** Describes the table for screen readers (visually hidden). */
  caption: string
  loading?: boolean
  loadingRows?: number
  /** Shown instead of the table when there are no rows (and not loading). */
  empty?: ReactNode
  className?: string
}

function cellClasses<T>(column: Column<T>) {
  return cn(
    'px-3 first:pl-5 last:pr-5',
    column.align === 'right' ? 'text-right' : 'text-left',
    column.hideBelow && HIDE_BELOW[column.hideBelow],
    column.grow && 'w-full max-w-0',
    column.className,
  )
}

/** A responsive data table: columns can hide on small screens, and the wrapper scrolls if needed. */
export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  caption,
  loading = false,
  loadingRows = 5,
  empty,
  className,
}: DataTableProps<T>) {
  if (!loading && rows.length === 0 && empty) return <>{empty}</>

  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full text-body" aria-busy={loading || undefined}>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border text-meta text-muted-foreground">
            {columns.map((column) => (
              <th key={column.key} scope="col" className={cn(cellClasses(column), 'py-2.5 font-medium whitespace-nowrap')}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {loading
            ? Array.from({ length: loadingRows }, (_, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column.key} className={cn(cellClasses(column), 'py-3.5')}>
                      <Skeleton
                        className={cn('h-4', column.align === 'right' ? 'ml-auto w-10' : column.grow ? 'w-3/4' : 'w-16')}
                      />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row) => (
                <tr key={getRowKey(row)}>
                  {columns.map((column) => (
                    <td key={column.key} className={cn(cellClasses(column), 'py-3')}>
                      {column.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  )
}
