# Competitor analysis

**Status:** ✅ Done. Heron studied 2026-10-29; adjacent tools listed below.

Part of [01 · Idea](../README.md) in the [Lintel SaaS plan](../../README.md).

## 1. Heron AI (heronaiapp.com), the reference

### How it was studied
Only what a normal visitor sees: the six public pages (home, chat widget, dashboard, pricing, about, contact), read in the built-in browser. One REA `capture_browser_scenario` run (headless Chrome, home page, network and page errors) recorded which hosts the page loads; its evidence ID is `ev_94c9ff6d763ae65d85b898ac706efecd9c54188b053606cccb1f255be09b5463`.

No sign-up, no form submissions, no backend calls, no scraping beyond those pages. `analyze_web_bundle` was not run because it needs a running Chrome DevTools endpoint. There is also no application bundle to analyse: the site is marketing pages only.

### What Heron is (and isn't)
- **A concept, not a shipping product.** The footer reads "concept crafted by Bearplus", the hero calls it a concept by an award-winning design agency, and the site has an Awwwards listing. The newsletter box is Bearplus's ("Want to see more cool websites like this?").
  - There's no sign-in, no download and no plugin listing. Every call to action is "Contact us" or "Book a demo".
- **The "about" copy contradicts itself.** One founder bio mentions "Kestrel Labs" and compliance and risk management in architecture and construction. The two addresses on the site are in Denver and Sydney (Bearplus's office).
- **What this means for us:** the market framing is credible (it echoes real products, see §2), but nobody has shipped Heron's promise yet: an in-tool agent across Revit, Rhino, ArchiCAD and SketchUp that edits only after approval. That gap is our opening. It also means Heron's prices are a designer's guess, not market-tested.

### Positioning and copy themes (paraphrased)
- **Promise:** an agent that lives inside your design tool. It reviews the model, flags issues, proposes fixes, and edits only after you approve.
- **Problem framing:** design tools are passive. Generic AI sits outside the model, so you re-explain context. Nothing watches for problems, and small tasks add up to lost days.
- **Workflow:** **Observe → Advise → Act (with approval) → Learn (firm standards)**.
- **Audience:** architects, interior designers, landscape architects, engineers, BIM managers, drafters, design leads and small firms.
- **Hero visual:** violation cards with a code citation, a title and a one-line explanation. Examples: exit-access travel distance, door swing direction, accessible toilet turning space. Clicking a violation highlights it on the plan.

### Products
| Surface | What the site claims |
|---|---|
| **Chat widget** (in-tool) | Floats over the host app. Grounded in the open model. Takes actions after approval. Plain language, and asks when unsure. Every edit can be undone. Keeps context across hosts. Three steps: open the chat, ask or instruct, approve. Demo: "how much tempered glass is required" gets a quantity estimate in m² |
| **Dashboard** (web) | All projects in one view; an approval queue (approve or reject in one click); full history of what changed, when and why; team view (who approved what); firm standards ("set the rules once"); code Q&A that applies the code to your layout, occupancy and conditions. Three steps: connect the Revit model → real-time compliance checks against local codes and amendments → resolve with suggestions mapped to citations ("cut review time by up to 80%") |

### Supported hosts
Revit is first ("In-tool agent in Revit" in the Standard tier). Rhino, ArchiCAD and SketchUp are listed as "More tools" on paid plans, with "more on the way".

### Pricing (as published)
| | Free | Standard | Business | Enterprise |
|---|---|---|---|---|
| Price | $0 | $99/mo (yearly toggle shows $90) | $295/mo (yearly $290) | Custom |
| For | Individuals exploring | Individuals and small firms editing in Revit | Medium, multi-office firms | Large firms, universities |
| Chat: ask about your model | ✓ | ✓ | ✓ | ✓ |
| Projects | 1 | Unlimited | Unlimited | Unlimited |
| In-tool agent (Revit), suggestions, edit on approval | — | ✓ | ✓ | ✓ |
| Other hosts (Rhino, ArchiCAD, SketchUp) | — | ✓ | ✓ | ✓ |
| Firm standards it learns | — | ✓ | ✓ | ✓ |
| Dashboard, team view and shared approvals | — | — | ✓ | ✓ |
| Admin, SSO, audit logs; API and data export | — | — | ✓ | ✓ |
| Support | Community | Email | Email + chat | Priority |
| Top-up credits | — | ✓ | ✓ | ✓ |

- Billing is monthly or yearly ("save 15%"). The yearly figures look like per-month equivalents, though the label reads "/year".
- Paid plans advertise a free trial. Credits suggest LLM usage is metered behind the seats.

### FAQ promises we must match
- Never changes the model without asking.
- Every edit is undoable.
- Uses only the parts of the model you share.
- Model data is processed under contract with the AI providers.
- Business tier adds SSO and audit logs.
- Reads the model you're working in, not just the open view.
- No special commands to learn.

### Integrations
Only the four host apps. No APIs, connectors, Slack or other integrations are shown; "API & data export" appears as a Business-tier line item.

### Front-end stack (from page load evidence)
- **Site:** Webflow site (meta generator "Webflow", `cdn.prod.website-files.com`), proxied through Netlify (`heronai-bp.netlify.app/config.js`, `/.netlify/scripts/rum`). jQuery 3.5.1 comes from Webflow.
- **Motion:** GSAP 3.12/3.13 with ScrollTrigger, SplitText and TextPlugin; Lenis smooth scroll; Barba.js page transitions with prefetch; Swiper carousels. A fake "boot sequence" preloader ("001 initialize core system …").
- **Analytics:** Microsoft Clarity, Mixpanel, Google Analytics 4, Bing UET.
- **Hosts contacted on load:** heronaiapp.com, cdn.prod.website-files.com, cdn.jsdelivr.net, unpkg.com, cloudfront (Webflow jQuery), heronai-bp.netlify.app, clarity.ms, googletagmanager, google-analytics, mxpnl, bing.
- **Design language:** off-white paper background, a thin orange-red rule, all-caps monospace labels with [01]-style indices, an architectural drawing feel.

**Our rule:** use none of this. Lintel gets its own name, palette, type and copy.

## 2. Adjacent real products (to verify in Validation)
| Product | Category | Relevance |
|---|---|---|
| UpCodes (+ UpCodes AI / Copilot, Revit plugin) | Searchable building codes, code Q&A, Revit checks | Closest real competitor for the "dashboard code questions" side. Strong code library (licensed) |
| Solibri | Rule-based IFC model checking (Nemetschek) | Desktop QA/QC leader. Rules, no agent, no edits in the host |
| Autodesk Model Checker / Revit Model Review | Free rule checkers for Revit | Report only, no edits, no chat |
| Archistar / CivCheck, Avolution | AI plan review for permitting | Plan-review side (jurisdictions), not in the authoring tool |
| Pele/ArkDesign/Snaptrude AI | AI layout generation | Generative, not a review-and-approve copilot |
| Rhino.Inside / Grasshopper scripts, pyRevit tools | DIY automation | What firms do today: scripts by a BIM manager, no NL, no audit |
| ChatGPT/Claude used outside the tool | Generic AI | The "disjointed" pain Heron names: no model context |

**Gap Lintel targets:** an agent that runs **inside the authoring tool**, applies **the firm's own rules** (with code-section references, not copied code text), proposes **edits as a reviewable diff**, and keeps a **complete audit trail**, starting on hosts small firms can afford.
