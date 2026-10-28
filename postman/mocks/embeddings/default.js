// Subset of the embedding API contract. Synthetic vectors exercise transport/shape handling, not semantic quality.
const http = require('http');
http.createServer((req, res) => {
  if (req.method !== 'POST' || req.url !== '/v1/embeddings') {
    res.writeHead(501); return res.end('Not modeled');
  }
  const body = req.body;
  if (!body || !Array.isArray(body.input) || !body.model || !Number.isInteger(body.dimensions)) {
    res.writeHead(400); return res.end(JSON.stringify({error: 'Invalid embedding request'}));
  }
  const malformed = body.input.some(text => text.includes('malformed-vector-fixture'));
  res.writeHead(200, {'Content-Type': 'application/json'});
  res.end(JSON.stringify({object: 'list', data: body.input.map((text, index) => ({
    index, object: 'embedding', embedding: Array.from({length: malformed ? 1 : body.dimensions}, (_, i) => i === 0 ? 1 : 0)
  }))}));
}).listen(process.env.PORT || 4500);
