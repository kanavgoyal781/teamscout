# M23 WCAG AA contrast audit

Computed relative luminance ratios (WCAG 2.1). AA normal text ≥4.5; large/bold ≥3.0.

| Pair | FG | BG | Ratio | AA normal |
|---|---|---|---:|:---:|
| Light ink on bg | `#0C1F3F` | `#F7F4ED` | **14.90:1** | yes |
| Light cream on navy | `#F7F4ED` | `#0C1F3F` | **14.90:1** | yes |
| Light muted on bg | `#5C6B82` | `#F7F4ED` | **4.93:1** | yes |
| Light warning on bg | `#8A5A22` | `#F7F4ED` | **5.36:1** | yes |
| Light brass on cream | `#7A6236` | `#F7F4ED` | **5.27:1** | yes |
| Light cream on brass badge | `#F7F4ED` | `#7A6236` | **5.27:1** | yes |
| Dark ink on bg | `#F2EDE2` | `#0A182E` | **15.20:1** | yes |
| Dark brass on navy | `#C4A86A` | `#0A182E` | **7.74:1** | yes |
| Dark danger on bg | `#D46A62` | `#0A182E` | **5.10:1** | yes |
| Dark warning on bg | `#C4924A` | `#0A182E` | **6.39:1** | yes |

## Notes
- Navy on cream and cream on navy both clear **~15:1**.
- Light brass token set to **#7A6236** (darkened from brief’s #A8894F) so cream badge text and brass chrome clear **≥5.2:1** AA.
- Warning light **#8A5A22** (≥5.3:1) for missing-skill outline labels.
- Dark danger **#D46A62** (≥5.1:1). Dark brass remains #C4A86A (~7.7:1 on navy).
- Brass remains **chrome-only** in product UI (score-ring, Best match badge, active nav) + About active/flow highlight.
