// Set this to your deployed agent API (Render / Hugging Face Space) before deploying to Vercel.
window.API_BASE = (location.hostname === "localhost" || location.hostname === "127.0.0.1")
  ? "http://localhost:8000"
  : "https://shopbot-api-chi.vercel.app";
