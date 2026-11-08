import react from "@vitejs/plugin-react";
import { createLogger, defineConfig } from "vite";

// Custom logger: silences harmless WS proxy disconnect noise that Vite
// emits through its own internal handlers (configure() alone doesn't stop them).
const SUPPRESS_PATTERNS = [
  /ws proxy (socket )?error/i,
  /ECONNABORTED/,
  /ECONNRESET/,
  /EPIPE/,
];

const logger = createLogger();
const _origWarn  = logger.warn.bind(logger);
const _origError = logger.error.bind(logger);

logger.warn  = (msg, opts) => { if (!SUPPRESS_PATTERNS.some(r => r.test(msg))) _origWarn(msg, opts); };
logger.error = (msg, opts) => { if (!SUPPRESS_PATTERNS.some(r => r.test(msg))) _origError(msg, opts); };

export default defineConfig({
  customLogger: logger,
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8001",
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          const suppress = new Set(["ECONNABORTED", "ECONNRESET", "EPIPE"]);
          proxy.on("error",          (err: any) => { if (!suppress.has(err.code)) console.error("proxy error", err); });
          proxy.on("proxyReqWsError",(err: any) => { if (!suppress.has(err.code)) console.error("proxy ws error", err); });
          proxy.on("open", (sock: any) => sock.on("error", (err: any) => { if (!suppress.has(err.code)) console.error("proxy socket error", err); }));
        },
      },
    },
  },
});
