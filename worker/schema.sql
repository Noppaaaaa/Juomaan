-- D1-skeema äänestykselle.
-- client_id = selaimen yksilöivä satunnaistunnus (localStorage).
-- product_key = "nimi||alkoholi_prosentti||hinta_eur".
-- PRIMARY KEY estää saman käyttäjän tuplaäänen samalle juomalle.
CREATE TABLE IF NOT EXISTS votes (
  client_id   TEXT    NOT NULL,
  product_key TEXT    NOT NULL,
  created_at  INTEGER NOT NULL,
  PRIMARY KEY (client_id, product_key)
);

CREATE INDEX IF NOT EXISTS idx_votes_product ON votes (product_key);
