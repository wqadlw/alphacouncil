import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// The token layer moved to `styles/globals.css` per `docs/FRONTEND_STYLE_GUIDE.md`
// §9, which puts stylesheets in one place instead of beside the entry point.
// `index.css` is gone rather than left as a second source of the same tokens.
import './styles/globals.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
