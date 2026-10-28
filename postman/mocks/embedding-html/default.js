const http = require('http');
http.createServer((req, res) => {
  res.writeHead(502, {'Content-Type': 'text/html'});
  res.end('<html><body>Upstream proxy unavailable</body></html>');
}).listen(process.env.PORT || 4500);
