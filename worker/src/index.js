// Cloudflare Worker: juomaan.fi äänestys-API (dokattavuus = maku/alkoholi-suhde).
// Tallentaa äänet D1-tietokantaan. Jokaisella käyttäjällä (selain-clientId) on
// enintään MAX_VOTES ääntä, ja yksi ääni per juoma.

const MAX_VOTES = 3;

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

function json(data, status, origin) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      ...corsHeaders(origin),
    },
  });
}

async function omatAanet(env, clientId) {
  const mine = await env.DB.prepare(
    "SELECT product_key FROM votes WHERE client_id = ?"
  ).bind(clientId).all();
  return mine.results.map((r) => r.product_key);
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin");

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    const url = new URL(request.url);
    if (!url.pathname.endsWith("/api/votes")) {
      return json({ error: "not_found" }, 404, origin);
    }

    // GET: palauta äänimäärät kaikille tuotteille + tämän käyttäjän äänet.
    if (request.method === "GET") {
      const clientId = (url.searchParams.get("clientId") || "").slice(0, 64);
      const tallies = await env.DB.prepare(
        "SELECT product_key, COUNT(*) AS c FROM votes GROUP BY product_key"
      ).all();
      const aanet = {};
      for (const r of tallies.results) aanet[r.product_key] = r.c;
      const omat = clientId ? await omatAanet(env, clientId) : [];
      return json({ aanet, omat, max: MAX_VOTES }, 200, origin);
    }

    // POST: anna yksi ääni juomalle. Body: { clientId, key }.
    if (request.method === "POST") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "bad_json" }, 400, origin);
      }
      const clientId = (body.clientId || "").toString().slice(0, 64);
      const key = (body.key || "").toString().slice(0, 300);
      if (!clientId || !key) {
        return json({ error: "missing_fields" }, 400, origin);
      }

      const already = await env.DB.prepare(
        "SELECT 1 FROM votes WHERE client_id = ? AND product_key = ?"
      ).bind(clientId, key).first();

      if (!already) {
        const cnt = await env.DB.prepare(
          "SELECT COUNT(*) AS c FROM votes WHERE client_id = ?"
        ).bind(clientId).first();
        if ((cnt?.c || 0) >= MAX_VOTES) {
          return json(
            { error: "no_votes_left", omat: await omatAanet(env, clientId), max: MAX_VOTES },
            409,
            origin
          );
        }
        await env.DB.prepare(
          "INSERT OR IGNORE INTO votes (client_id, product_key, created_at) VALUES (?, ?, ?)"
        ).bind(clientId, key, Date.now()).run();
      }

      const total = await env.DB.prepare(
        "SELECT COUNT(*) AS c FROM votes WHERE product_key = ?"
      ).bind(key).first();

      return json(
        { ok: true, key, count: total?.c || 0, omat: await omatAanet(env, clientId), max: MAX_VOTES },
        200,
        origin
      );
    }

    // DELETE: peru oma ääni. Body: { clientId, key }.
    if (request.method === "DELETE") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "bad_json" }, 400, origin);
      }
      const clientId = (body.clientId || "").toString().slice(0, 64);
      const key = (body.key || "").toString().slice(0, 300);
      if (!clientId || !key) {
        return json({ error: "missing_fields" }, 400, origin);
      }

      await env.DB.prepare(
        "DELETE FROM votes WHERE client_id = ? AND product_key = ?"
      ).bind(clientId, key).run();

      const total = await env.DB.prepare(
        "SELECT COUNT(*) AS c FROM votes WHERE product_key = ?"
      ).bind(key).first();

      return json(
        { ok: true, key, count: total?.c || 0, omat: await omatAanet(env, clientId), max: MAX_VOTES },
        200,
        origin
      );
    }

    return json({ error: "method_not_allowed" }, 405, origin);
  },
};
