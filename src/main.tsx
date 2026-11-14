import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

const fontLink = document.createElement('link');
fontLink.rel = 'stylesheet';
fontLink.href = 'https://fonts.googleapis.com/css2?family=Onest:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap';
document.head.appendChild(fontLink);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
