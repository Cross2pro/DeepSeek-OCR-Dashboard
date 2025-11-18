const express = require('express');
const path = require('path'); // Import path module
const app = express();
const port = 3000;

// Serve static files from the 'production' directory
app.use(express.static(path.join(__dirname, '../dist')));

app.get('/', (req, res) => {
  res.send('Hello World!');
});

// Catch-all route to serve index.html for SPA routing (Express 5+ with router@2 / path-to-regexp@^8)
// Use a native RegExp for a true catch-all.
app.get(/.*/, (req, res) => {
  res.sendFile(path.join(__dirname, '../production', 'index.html'));
});

app.listen(port, () => {
  console.log(`Backend server listening at http://localhost:${port}`);
});
