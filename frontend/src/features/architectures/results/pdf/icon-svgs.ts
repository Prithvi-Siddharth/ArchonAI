/**
 * The official AWS icon SVGs as text. Only imported by the PDF generator, which is itself loaded on
 * demand, so these files never weigh on the normal app bundle.
 */
const files = import.meta.glob<string>('../../../../assets/aws-icons/*.svg', { query: '?raw', import: 'default', eager: true })

export const ICON_SVGS: ReadonlyMap<string, string> = new Map(
  Object.entries(files).map(([path, svg]) => [path.slice(path.lastIndexOf('/') + 1).replace(/\.svg$/, ''), svg]),
)
