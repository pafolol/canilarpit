/**
 * Frontend-only dev server.
 *
 * Serves backend/content/guides/*.json through the real API shapes so the
 * interface runs with no database and no API process. It only reads those
 * files; nothing server-side is started or modified.
 *
 *   npm run dev:mock
 */
import fs from 'node:fs'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const GUIDES = path.resolve(import.meta.dirname, '../backend/content/guides')

type Row = Record<string, any>

function load(): Row[] {
  return fs
    .readdirSync(GUIDES)
    .filter((f) => f.endsWith('.json'))
    .map((f) => {
      const d = JSON.parse(fs.readFileSync(path.join(GUIDES, f), 'utf8'))
      const slug = d.category_slug || 'general'
      return {
        id: d.slug,
        slug: d.slug,
        title: d.title,
        summary: d.summary,
        guide_type: d.guide_type,
        category: { id: slug, slug, title: slug[0].toUpperCase() + slug.slice(1) },
        larp: {
          entry_type: d.content.larp.entry_type,
          verdict: d.content.larp.verdict,
          exposure_seconds: d.content.larp.exposure_seconds ?? null,
          unfalsifiable: !!d.content.larp.unfalsifiable,
          flags: d.content.larp.flags ?? [],
          dek: d.content.larp.dek ?? '',
        },
        published_at: '2026-08-01T00:00:00Z',
        _detail: {
          revision_id: d.slug,
          revision_number: 1,
          content: { extra_sections: [], ...d.content },
          aliases: d.aliases ?? [],
          sources: d.sources ?? [],
          media: [],
          last_verified_at: d.last_verified_at ?? null,
        },
      }
    })
}

const card = ({ _detail, ...rest }: Row) => rest

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'guide-fixtures',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const url = new URL(req.url || '/', 'http://local')
          if (!url.pathname.startsWith('/api/v1')) return next()

          const rows = load()
          const route = url.pathname.replace('/api/v1', '')
          const send = (body: unknown, status = 200) => {
            res.statusCode = status
            res.setHeader('content-type', 'application/json')
            res.end(JSON.stringify(body))
          }

          if (route === '/config') return send({ site_name: 'canilarpit' })

          if (route === '/categories') {
            const seen = new Map<string, Row>()
            for (const r of rows) {
              if (!seen.has(r.category.slug))
                seen.set(r.category.slug, {
                  ...r.category,
                  description: '',
                  sort_order: 0,
                  published_guide_count: 0,
                })
              seen.get(r.category.slug)!.published_guide_count++
            }
            return send([...seen.values()])
          }

          const one = route.match(/^\/guides\/([^/]+)$/)
          if (one) {
            const row = rows.find((r) => r.slug === decodeURIComponent(one[1]))
            if (!row) return send({ detail: 'Not found' }, 404)
            return send({ ...card(row), ...row._detail })
          }

          const near = route.match(/^\/guides\/([^/]+)\/related$/)
          if (near) {
            const me = rows.find((r) => r.slug === decodeURIComponent(near[1]))
            return send(
              rows.filter((r) => r !== me && r.category.slug === me?.category.slug).slice(0, 6).map(card),
            )
          }

          if (route === '/guides') {
            const q = (url.searchParams.get('q') || '').trim().toLowerCase()
            const category = url.searchParams.get('category')
            const types = url.searchParams.getAll('entry_type')
            const verdicts = url.searchParams.getAll('verdict')

            let items = rows.filter(
              (r) =>
                (!category || r.category.slug === category) &&
                (!types.length || types.includes(r.larp.entry_type)) &&
                (!verdicts.length || verdicts.includes(r.larp.verdict)) &&
                (!q ||
                  [r.title, r.summary, ...(r._detail.aliases || [])]
                    .join(' ')
                    .toLowerCase()
                    .includes(q)),
            )

            if (q) {
              const rank = (r: Row) => {
                const t = r.title.toLowerCase()
                return t.startsWith(q) ? 0 : t.includes(q) ? 1 : 2
              }
              items = items.sort((a, b) => rank(a) - rank(b) || a.title.localeCompare(b.title))
            } else if (url.searchParams.get('sort') === 'title') {
              items = items.sort((a, b) => a.title.localeCompare(b.title))
            }

            const size = Number(url.searchParams.get('page_size') || 20)
            return send({
              items: items.slice(0, size).map(card),
              pagination: { page: 1, page_size: size, total: items.length, pages: 1 },
            })
          }

          return send({ detail: 'Not found' }, 404)
        })
      },
    },
  ],
  server: { port: Number(process.env.PORT) || 5173 },
})
