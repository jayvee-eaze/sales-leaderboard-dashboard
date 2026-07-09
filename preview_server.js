// Local preview only. Not part of the deployed artifact (GitHub Pages serves index.html
// as a static file directly, no server needed in production).
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3001;
const ROOT = __dirname;

http.createServer((req, res) => {
  let filePath = path.join(ROOT, req.url === '/' ? 'index.html' : req.url);
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    const ext = path.extname(filePath);
    const type = ext === '.html' ? 'text/html' : ext === '.json' ? 'application/json' : 'text/plain';
    res.writeHead(200, { 'Content-Type': type });
    res.end(data);
  });
}).listen(PORT, () => console.log('preview server on http://localhost:' + PORT));
