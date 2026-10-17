async function load(id) { const r = await fetch(`data/${id}.json`); return r.json() }
