# Forge Implementation Guide

This guide walks through building Forge — a fork of [Kiln](https://github.com/otaleghani/kiln) v0.9.5 that adds overlay injection, API reverse proxying, and static asset serving to Kiln's existing `dev` command. Follow each step in order. Every step includes verification criteria — do not proceed until your step passes.

**Prerequisites**: Go 1.25+, git, a terminal, and a text editor. Familiarity with Go's `net/http` package, `httputil.ReverseProxy`, and `http.FileServer`.

**Reference**: Read `SIMPLIFIED_CONCEPT.md` §Repository 1 before starting. That is the authoritative spec; this guide provides implementation-level detail.

---

## Step 0: Fork and set up the repository

### What to do

1. Fork `github.com/otaleghani/kiln` at tag `v0.9.5` into a new repository named `forge`.
2. Rename the Go module:
   - In `go.mod`, change the module path from `github.com/otaleghani/kiln` to your org's forge module path (e.g., `github.com/YOUR_ORG/forge`).
   - Run `find . -type f -name '*.go' -exec sed -i 's|github.com/otaleghani/kiln|github.com/YOUR_ORG/forge|g' {} +` to update all import paths.
3. Rename the CLI binary:
   - Rename `cmd/kiln/` to `cmd/forge/`.
   - In `cmd/forge/main.go`, update any display strings from "kiln" to "forge" (e.g., the root command name).
4. Run `go mod tidy` to clean up dependencies.
5. Create the new package directories:
   ```
   mkdir -p internal/overlay
   mkdir -p internal/proxy
   mkdir -p static
   ```
6. Commit as "fork: rename kiln → forge, update module path".

### Verify

```bash
go build ./cmd/forge
./forge --help            # Should print forge CLI help
./forge dev --help        # Should print dev subcommand flags (--input, --output, --port, etc.)
go vet ./...              # No errors
```

---

## Step 1: Add new CLI flags to the `dev` command

### What to do

Open the dev command definition (likely `internal/cli/dev.go` or wherever `cmdDev` is defined). Add three new flags:

```go
var proxyBackend string
var overlayDir   string
var injectOverlay bool
```

Register them with Cobra in the command's `init()` or flag setup:

```go
cmdDev.Flags().StringVar(&proxyBackend, "proxy-backend", "", "URL to forward /api/* requests to (e.g., http://127.0.0.1:8081)")
cmdDev.Flags().StringVar(&overlayDir, "overlay-dir", "", "Directory containing overlay static assets served at /ops/*")
cmdDev.Flags().BoolVar(&injectOverlay, "inject-overlay", false, "Inject overlay CSS/JS tags into HTML responses")
```

Make sure these flags are accessible from the `runDev` function (passed as parameters or available via the command's flag set).

### Verify

```bash
go build ./cmd/forge
./forge dev --help
```

Confirm the help output lists `--proxy-backend`, `--overlay-dir`, and `--inject-overlay` with their descriptions and defaults. Also confirm all existing Kiln flags still appear.

```bash
# Confirm it still works as plain kiln — existing behavior unbroken
# (requires a test vault; use the demo vault from obsidian-ops)
./forge dev --input /path/to/demo/vault --output /tmp/forge-test --port 9090
# Visit http://localhost:9090 in browser — should render the vault site
```

---

## Step 2: Implement overlay static file serving (`/ops/*`)

This is the simplest new feature — start here to build confidence.

### What to do

Create `internal/overlay/static.go`:

```go
package overlay

import (
	"net/http"
	"os"
)

// NewStaticHandler returns an http.Handler that serves files from dir
// at the /ops/ URL prefix. Returns nil if dir is empty or does not exist.
func NewStaticHandler(dir string) http.Handler {
	if dir == "" {
		return nil
	}
	if info, err := os.Stat(dir); err != nil || !info.IsDir() {
		return nil
	}
	return http.StripPrefix("/ops/", http.FileServer(http.Dir(dir)))
}
```

### Verify

Create `internal/overlay/static_test.go`:

```go
package overlay_test

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"YOUR_MODULE/internal/overlay"
)

func TestNewStaticHandler_ServesFiles(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "ops.css"), []byte("body{}"), 0644)
	os.WriteFile(filepath.Join(dir, "ops.js"), []byte("console.log('ok')"), 0644)

	handler := overlay.NewStaticHandler(dir)
	if handler == nil {
		t.Fatal("expected non-nil handler")
	}

	// Test CSS
	req := httptest.NewRequest("GET", "/ops/ops.css", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if rec.Body.String() != "body{}" {
		t.Fatalf("unexpected body: %s", rec.Body.String())
	}

	// Test JS
	req = httptest.NewRequest("GET", "/ops/ops.js", nil)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	// Test 404 for missing file
	req = httptest.NewRequest("GET", "/ops/missing.txt", nil)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != 404 {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
}

func TestNewStaticHandler_EmptyDir(t *testing.T) {
	if overlay.NewStaticHandler("") != nil {
		t.Fatal("expected nil for empty dir")
	}
}

func TestNewStaticHandler_NonexistentDir(t *testing.T) {
	if overlay.NewStaticHandler("/nonexistent/path") != nil {
		t.Fatal("expected nil for nonexistent dir")
	}
}
```

```bash
go test ./internal/overlay/ -v -run TestNewStaticHandler
```

All tests must pass.

---

## Step 3: Implement the API reverse proxy (`/api/*`)

### What to do

Create `internal/proxy/reverse.go`:

```go
package proxy

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"
)

// NewReverseProxy returns an http.Handler that forwards requests to the
// given backend URL. Returns nil if backendURL is empty.
//
// The proxy preserves the original request path (including /api/ prefix),
// all headers, query parameters, and request body. It uses a 180-second
// response timeout to accommodate long-running agent operations.
func NewReverseProxy(backendURL string) (http.Handler, error) {
	if backendURL == "" {
		return nil, nil
	}

	target, err := url.Parse(backendURL)
	if err != nil {
		return nil, err
	}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			// Preserve the original path (e.g., /api/apply)
			// Do NOT rewrite the path — the agent expects /api/* paths.
			req.Host = target.Host
		},
	}

	// Use a transport with a generous timeout for long-running agent ops.
	proxy.Transport = &http.Transport{
		ResponseHeaderTimeout: 180 * time.Second,
	}

	return proxy, nil
}
```

### Verify

Create `internal/proxy/reverse_test.go`:

```go
package proxy_test

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"YOUR_MODULE/internal/proxy"
)

func TestNewReverseProxy_ForwardsRequest(t *testing.T) {
	// Mock backend that echoes request details
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Test-Header", "echoed")
		w.WriteHeader(200)
		w.Write([]byte(`{"path":"` + r.URL.Path + `","method":"` + r.Method + `"}`))
	}))
	defer backend.Close()

	handler, err := proxy.NewReverseProxy(backend.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if handler == nil {
		t.Fatal("expected non-nil handler")
	}

	// POST /api/apply
	body := strings.NewReader(`{"instruction":"test"}`)
	req := httptest.NewRequest("POST", "/api/apply", body)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != 200 {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	respBody, _ := io.ReadAll(rec.Body)
	if !strings.Contains(string(respBody), `"/api/apply"`) {
		t.Fatalf("path not preserved: %s", respBody)
	}
	if rec.Header().Get("X-Test-Header") != "echoed" {
		t.Fatal("response headers not forwarded")
	}
}

func TestNewReverseProxy_PreservesQueryParams(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(r.URL.RawQuery))
	}))
	defer backend.Close()

	handler, _ := proxy.NewReverseProxy(backend.URL)
	req := httptest.NewRequest("GET", "/api/health?verbose=true", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if !strings.Contains(rec.Body.String(), "verbose=true") {
		t.Fatalf("query params not preserved: %s", rec.Body.String())
	}
}

func TestNewReverseProxy_EmptyURL(t *testing.T) {
	handler, err := proxy.NewReverseProxy("")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if handler != nil {
		t.Fatal("expected nil handler for empty URL")
	}
}

func TestNewReverseProxy_InvalidURL(t *testing.T) {
	_, err := proxy.NewReverseProxy("://bad-url")
	if err == nil {
		t.Fatal("expected error for invalid URL")
	}
}

func TestNewReverseProxy_BackendDown(t *testing.T) {
	// Point at a port that's not listening
	handler, err := proxy.NewReverseProxy("http://127.0.0.1:19999")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	req := httptest.NewRequest("GET", "/api/health", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	// Should get a 502 Bad Gateway
	if rec.Code != 502 {
		t.Fatalf("expected 502, got %d", rec.Code)
	}
}

func TestNewReverseProxy_LargeRequestBody(t *testing.T) {
	var receivedLen int
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		receivedLen = len(body)
		w.WriteHeader(200)
	}))
	defer backend.Close()

	handler, _ := proxy.NewReverseProxy(backend.URL)
	largeBody := strings.Repeat("x", 10000)
	req := httptest.NewRequest("POST", "/api/apply", strings.NewReader(largeBody))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if receivedLen != 10000 {
		t.Fatalf("expected body length 10000, got %d", receivedLen)
	}
}

func TestNewReverseProxy_SlowBackend(t *testing.T) {
	// Verify the proxy doesn't time out prematurely for a reasonable delay
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(500 * time.Millisecond)
		w.WriteHeader(200)
		w.Write([]byte("ok"))
	}))
	defer backend.Close()

	handler, _ := proxy.NewReverseProxy(backend.URL)
	req := httptest.NewRequest("GET", "/api/health", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != 200 {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
}
```

```bash
go test ./internal/proxy/ -v -run TestNewReverseProxy
```

All tests must pass.

---

## Step 4: Implement HTML injection middleware

This is the most involved new component. It wraps an existing `http.Handler` and injects overlay tags into HTML responses.

### What to do

Create `internal/overlay/inject.go`:

```go
package overlay

import (
	"bytes"
	"net/http"
	"strings"
)

// injectionSnippet is the HTML inserted before </head>.
const injectionSnippet = `<!-- ops-overlay -->
<link rel="stylesheet" href="/ops/ops.css">
<script src="/ops/ops.js" defer></script>
`

// headCloseTag is searched case-insensitively.
var headCloseBytes = []byte("</head>")

// InjectMiddleware wraps handler and injects overlay tags into HTML responses.
// If enabled is false, it returns handler unchanged.
func InjectMiddleware(handler http.Handler, enabled bool) http.Handler {
	if !enabled {
		return handler
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Only intercept GET/HEAD requests — API and other methods pass through.
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			handler.ServeHTTP(w, r)
			return
		}

		rec := &responseRecorder{
			header: make(http.Header),
		}
		handler.ServeHTTP(rec, r)

		body := rec.body.Bytes()
		contentType := rec.header.Get("Content-Type")

		// Only inject into HTML responses.
		if strings.Contains(contentType, "text/html") {
			body = injectIntoHTML(body)
		}

		// Copy headers from recorded response, but remove Content-Length
		// since injection changes the body size. Go's HTTP server will
		// handle chunked encoding or set Content-Length automatically.
		for k, vals := range rec.header {
			if strings.EqualFold(k, "Content-Length") {
				continue
			}
			for _, v := range vals {
				w.Header().Add(k, v)
			}
		}

		w.WriteHeader(rec.statusCode)
		w.Write(body)
	})
}

// injectIntoHTML finds </head> (case-insensitive) and inserts the snippet.
func injectIntoHTML(body []byte) []byte {
	lower := bytes.ToLower(body)
	idx := bytes.Index(lower, headCloseBytes)
	if idx < 0 {
		return body // No </head> found, return unchanged.
	}

	var buf bytes.Buffer
	buf.Grow(len(body) + len(injectionSnippet))
	buf.Write(body[:idx])
	buf.WriteString(injectionSnippet)
	buf.Write(body[idx:])
	return buf.Bytes()
}

// responseRecorder captures the upstream handler's response for post-processing.
type responseRecorder struct {
	header     http.Header
	body       bytes.Buffer
	statusCode int
}

func (r *responseRecorder) Header() http.Header {
	return r.header
}

func (r *responseRecorder) Write(b []byte) (int, error) {
	if r.statusCode == 0 {
		r.statusCode = 200
	}
	return r.body.Write(b)
}

func (r *responseRecorder) WriteHeader(code int) {
	r.statusCode = code
}
```

### Verify

Create `internal/overlay/inject_test.go`:

```go
package overlay_test

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"YOUR_MODULE/internal/overlay"
)

// htmlHandler returns a handler that serves the given HTML with text/html content type.
func htmlHandler(html string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(200)
		w.Write([]byte(html))
	})
}

// jsonHandler returns a handler that serves JSON.
func jsonHandler(json string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		w.Write([]byte(json))
	})
}

func TestInjectMiddleware_InjectsBeforeHeadClose(t *testing.T) {
	inner := htmlHandler("<html><head><title>Test</title></head><body></body></html>")
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("GET", "/", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	body := rec.Body.String()
	if !strings.Contains(body, "<!-- ops-overlay -->") {
		t.Fatal("injection marker not found")
	}
	if !strings.Contains(body, `<link rel="stylesheet" href="/ops/ops.css">`) {
		t.Fatal("CSS link not found")
	}
	if !strings.Contains(body, `<script src="/ops/ops.js" defer></script>`) {
		t.Fatal("JS script not found")
	}

	// Verify injection is BEFORE </head>
	overlayIdx := strings.Index(body, "<!-- ops-overlay -->")
	headIdx := strings.Index(body, "</head>")
	if overlayIdx > headIdx {
		t.Fatal("injection should appear before </head>")
	}
}

func TestInjectMiddleware_CaseInsensitiveHead(t *testing.T) {
	inner := htmlHandler("<HTML><HEAD><TITLE>Test</TITLE></HEAD><BODY></BODY></HTML>")
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("GET", "/", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if !strings.Contains(rec.Body.String(), "<!-- ops-overlay -->") {
		t.Fatal("case-insensitive injection failed")
	}
}

func TestInjectMiddleware_NoHeadTag(t *testing.T) {
	inner := htmlHandler("<html><body><p>No head tag</p></body></html>")
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("GET", "/", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	body := rec.Body.String()
	if strings.Contains(body, "ops-overlay") {
		t.Fatal("should not inject when no </head> tag exists")
	}
	if !strings.Contains(body, "No head tag") {
		t.Fatal("original content should be preserved")
	}
}

func TestInjectMiddleware_NonHTMLPassthrough(t *testing.T) {
	inner := jsonHandler(`{"status":"ok"}`)
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("GET", "/api/health", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	body := rec.Body.String()
	if strings.Contains(body, "ops-overlay") {
		t.Fatal("should not inject into non-HTML responses")
	}
	if body != `{"status":"ok"}` {
		t.Fatalf("JSON body corrupted: %s", body)
	}
}

func TestInjectMiddleware_Disabled(t *testing.T) {
	inner := htmlHandler("<html><head></head><body></body></html>")
	handler := overlay.InjectMiddleware(inner, false)

	req := httptest.NewRequest("GET", "/", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if strings.Contains(rec.Body.String(), "ops-overlay") {
		t.Fatal("disabled middleware should not inject")
	}
}

func TestInjectMiddleware_POSTPassthrough(t *testing.T) {
	inner := htmlHandler("<html><head></head><body></body></html>")
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("POST", "/", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if strings.Contains(rec.Body.String(), "ops-overlay") {
		t.Fatal("POST requests should not be injected")
	}
}

func TestInjectMiddleware_PreservesStatusCode(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(404)
		w.Write([]byte("<html><head></head><body>Not found</body></html>"))
	})
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("GET", "/missing", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != 404 {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
	// Should still inject into 404 HTML pages
	if !strings.Contains(rec.Body.String(), "ops-overlay") {
		t.Fatal("should inject into 404 HTML pages")
	}
}

func TestInjectMiddleware_PreservesOtherHeaders(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.Header().Set("X-Custom", "preserved")
		w.Header().Set("Cache-Control", "no-cache")
		w.WriteHeader(200)
		w.Write([]byte("<html><head></head><body></body></html>"))
	})
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("GET", "/", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Header().Get("X-Custom") != "preserved" {
		t.Fatal("custom header not preserved")
	}
	if rec.Header().Get("Cache-Control") != "no-cache" {
		t.Fatal("cache-control header not preserved")
	}
}

func TestInjectMiddleware_StripsContentLength(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		body := "<html><head></head><body></body></html>"
		w.Header().Set("Content-Length", "38")
		w.WriteHeader(200)
		w.Write([]byte(body))
	})
	handler := overlay.InjectMiddleware(inner, true)

	req := httptest.NewRequest("GET", "/", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	// Content-Length should be stripped (body size changed due to injection)
	if rec.Header().Get("Content-Length") != "" {
		t.Fatal("Content-Length should be stripped after injection")
	}
}
```

```bash
go test ./internal/overlay/ -v
```

All tests must pass.

---

## Step 5: Wire the new handlers into the `dev` command

This is the integration step. You will modify Kiln's existing `dev` command to compose the new handlers into the HTTP server's handler chain.

### What to do

Locate where the dev server sets up its HTTP handler (in `internal/server/server.go` or `internal/cli/dev.go` — look for `http.ListenAndServe`, `http.ServeMux`, or `http.Handle` calls). The existing Kiln server uses a handler chain that roughly looks like:

```
Request → Clean URL rewrite → File server (site dir) → 404 handler
```

You need to wrap/extend this to:

```
Request → /api/* prefix? → Yes → Reverse Proxy handler
                          → No  → /ops/* prefix? → Yes → Static file server (overlay dir)
                                                  → No  → Injection middleware → existing Kiln handler
```

**Implementation approach**: Create a new top-level `http.Handler` that routes by prefix. Add this to the server setup, replacing the raw Kiln handler.

Create `internal/server/mux.go` (or add to the existing server file):

```go
package server

import (
	"net/http"
	"strings"
)

// ForgeConfig holds the optional Forge extensions to the Kiln dev server.
type ForgeConfig struct {
	ProxyHandler   http.Handler // nil if --proxy-backend not set
	OverlayHandler http.Handler // nil if --overlay-dir not set
	InjectEnabled  bool         // --inject-overlay flag
}

// NewForgeHandler wraps the base Kiln handler with Forge's extensions.
// If no extensions are configured, returns baseHandler unchanged.
func NewForgeHandler(baseHandler http.Handler, cfg ForgeConfig) http.Handler {
	// Wrap the base handler with injection middleware (no-ops if disabled)
	injectedHandler := overlay.InjectMiddleware(baseHandler, cfg.InjectEnabled)

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Route /api/* to reverse proxy
		if cfg.ProxyHandler != nil && strings.HasPrefix(r.URL.Path, "/api/") {
			cfg.ProxyHandler.ServeHTTP(w, r)
			return
		}

		// Route /ops/* to overlay static files
		if cfg.OverlayHandler != nil && strings.HasPrefix(r.URL.Path, "/ops/") {
			cfg.OverlayHandler.ServeHTTP(w, r)
			return
		}

		// Everything else goes to Kiln with injection
		injectedHandler.ServeHTTP(w, r)
	})
}
```

Then modify `runDev` (the dev command's run function) to:

1. After creating the existing Kiln handler, construct the `ForgeConfig`.
2. Call `overlay.NewStaticHandler(overlayDir)` for the overlay handler.
3. Call `proxy.NewReverseProxy(proxyBackend)` for the proxy handler.
4. Wrap the Kiln handler: `handler = server.NewForgeHandler(kilnHandler, cfg)`.
5. Pass the wrapped handler to the HTTP server.

**How to find the right place**: Search the Kiln code for where `http.ListenAndServe` or `server.Serve` is called in the dev command flow. The existing handler is passed there — intercept it.

The exact integration point depends on Kiln's internal structure. You may need to:
- Export the base handler from the server package, or
- Add a hook/option to the `Serve` function for wrapping the handler, or
- Restructure `Serve` to accept an optional handler wrapper.

Choose the least invasive approach. Ideally, modify `Serve` to accept a `ForgeConfig` parameter (defaulting to zero-value/no-op if not provided).

### Verify

```bash
go build ./cmd/forge
go vet ./...
go test ./...
```

All must pass. Then do manual integration testing:

**Test 1: Forge without extensions (backwards compatibility)**

```bash
./forge dev --input /path/to/demo/vault --output /tmp/forge-test --port 9090
# Visit http://localhost:9090 — site should render exactly like kiln dev
# No overlay tags should appear in page source
```

**Test 2: Overlay static serving**

```bash
mkdir -p /tmp/overlay-test
echo "body { border: 5px solid red; }" > /tmp/overlay-test/ops.css
echo "console.log('forge overlay loaded')" > /tmp/overlay-test/ops.js

./forge dev --input /path/to/demo/vault --output /tmp/forge-test --port 9090 \
  --overlay-dir /tmp/overlay-test

curl -s http://localhost:9090/ops/ops.css
# Should print: body { border: 5px solid red; }

curl -s http://localhost:9090/ops/ops.js
# Should print: console.log('forge overlay loaded')
```

**Test 3: HTML injection**

```bash
./forge dev --input /path/to/demo/vault --output /tmp/forge-test --port 9090 \
  --overlay-dir /tmp/overlay-test --inject-overlay

curl -s http://localhost:9090/ | grep "ops-overlay"
# Should find the injection marker

curl -s http://localhost:9090/ | grep "ops.css"
# Should find the CSS link tag

curl -s http://localhost:9090/ | grep "ops.js"
# Should find the JS script tag
```

**Test 4: API proxying**

Start a simple mock backend first:

```bash
# In terminal 1: start a mock backend on port 8081
python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status':'ok','path':self.path}).encode())
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'ok':True,'received':body.decode()}).encode())
HTTPServer(('127.0.0.1', 8081), H).serve_forever()
"

# In terminal 2: start forge with proxy
./forge dev --input /path/to/demo/vault --output /tmp/forge-test --port 9090 \
  --proxy-backend http://127.0.0.1:8081 --overlay-dir /tmp/overlay-test --inject-overlay

# In terminal 3: test the proxy
curl -s http://localhost:9090/api/health
# Should return: {"status": "ok", "path": "/api/health"}

curl -s -X POST http://localhost:9090/api/apply \
  -H "Content-Type: application/json" \
  -d '{"instruction":"test"}'
# Should return: {"ok": true, "received": "{\"instruction\":\"test\"}"}

# Verify non-API paths still go to kiln
curl -s http://localhost:9090/ | grep "ops-overlay"
# Should still show injected overlay
```

---

## Step 6: Create the overlay assets (`ops.js` and `ops.css`)

### What to do

Copy `ops.css` from the current obsidian-ops `src/obsidian_ops/static/ops.css` into `static/ops.css` in the Forge repo. This file is used verbatim — no changes needed.

Create a **simplified** `static/ops.js` that replaces the SSE-based approach with synchronous fetch. The new JS must:

1. Create the same UI elements as the current `ops.js` (FAB button, modal with backdrop, textarea, submit button, summary area, progress area, refresh/undo buttons).
2. On submit, `POST /api/apply` with `{ instruction, current_url_path }` and wait for the JSON response.
3. Display results based on the response:
   - `ok && updated` → show success message + summary + refresh/undo buttons.
   - `ok && !updated` → show "No changes made" message.
   - `!ok` → show error message from `result.error`.
4. Undo button sends `POST /api/undo` and displays the result similarly.
5. Refresh button calls `window.location.reload()`.

Here is the simplified `ops.js`:

```javascript
(function () {
  "use strict";

  const state = { running: false };

  function getCurrentUrlPath() {
    return window.location.pathname;
  }

  function buildUI() {
    // FAB
    const fab = document.createElement("button");
    fab.id = "ops-fab";
    fab.textContent = "*";
    fab.title = "Open Obsidian Ops";
    document.body.appendChild(fab);

    // Backdrop
    const backdrop = document.createElement("div");
    backdrop.id = "ops-modal-backdrop";
    document.body.appendChild(backdrop);

    // Modal
    const modal = document.createElement("div");
    modal.id = "ops-modal";
    backdrop.appendChild(modal);

    // Header
    const header = document.createElement("div");
    header.id = "ops-header";
    modal.appendChild(header);

    const pageCtx = document.createElement("span");
    pageCtx.id = "ops-page-context";
    pageCtx.textContent = getCurrentUrlPath();
    header.appendChild(pageCtx);

    const closeBtn = document.createElement("button");
    closeBtn.id = "ops-close";
    closeBtn.textContent = "\u00d7";
    closeBtn.title = "Close";
    header.appendChild(closeBtn);

    // Textarea
    const textarea = document.createElement("textarea");
    textarea.id = "ops-instruction";
    textarea.rows = 4;
    textarea.placeholder = "Describe what you want to change\u2026";
    modal.appendChild(textarea);

    // Submit
    const submit = document.createElement("button");
    submit.id = "ops-submit";
    submit.textContent = "Run";
    modal.appendChild(submit);

    // Summary
    const summary = document.createElement("div");
    summary.id = "ops-summary";
    modal.appendChild(summary);

    // Progress
    const progress = document.createElement("div");
    progress.id = "ops-progress";
    modal.appendChild(progress);

    // Actions
    const actions = document.createElement("div");
    actions.id = "ops-actions";
    modal.appendChild(actions);

    const refreshBtn = document.createElement("button");
    refreshBtn.id = "ops-refresh";
    refreshBtn.textContent = "Refresh page";
    actions.appendChild(refreshBtn);

    const undoBtn = document.createElement("button");
    undoBtn.id = "ops-undo";
    undoBtn.textContent = "Undo";
    actions.appendChild(undoBtn);

    return { fab, backdrop, modal, textarea, submit, summary, progress, actions, closeBtn, refreshBtn, undoBtn };
  }

  function openModal(els) {
    els.backdrop.classList.add("ops-open");
    els.textarea.focus();
  }

  function closeModal(els) {
    if (state.running) return;
    els.backdrop.classList.remove("ops-open");
    resetState(els);
  }

  function resetState(els) {
    els.modal.classList.remove("ops-running", "ops-success", "ops-error");
    els.summary.textContent = "";
    els.progress.textContent = "";
    els.textarea.disabled = false;
    els.submit.disabled = false;
  }

  function setRunning(els) {
    state.running = true;
    els.modal.classList.add("ops-running");
    els.modal.classList.remove("ops-success", "ops-error");
    els.textarea.disabled = true;
    els.submit.disabled = true;
    els.progress.textContent = "Working\u2026";
    els.summary.textContent = "";
  }

  function setResult(els, result) {
    state.running = false;
    els.modal.classList.remove("ops-running");
    els.textarea.disabled = false;
    els.submit.disabled = false;
    els.progress.textContent = "";

    if (!result.ok) {
      els.modal.classList.add("ops-error");
      els.summary.textContent = result.error || "Unknown error";
      return;
    }

    els.modal.classList.add("ops-success");
    if (result.updated) {
      els.summary.textContent = result.summary || "Changes applied.";
    } else {
      els.summary.textContent = result.summary || "No changes made.";
    }
  }

  async function submitJob(els) {
    const instruction = els.textarea.value.trim();
    if (!instruction) return;

    setRunning(els);

    try {
      const resp = await fetch("/api/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction: instruction,
          current_url_path: getCurrentUrlPath(),
        }),
      });
      const result = await resp.json();
      setResult(els, result);
    } catch (err) {
      setResult(els, { ok: false, error: "Request failed: " + err.message });
    }
  }

  async function submitUndo(els) {
    setRunning(els);
    try {
      const resp = await fetch("/api/undo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const result = await resp.json();
      setResult(els, result);
    } catch (err) {
      setResult(els, { ok: false, error: "Undo failed: " + err.message });
    }
  }

  function init() {
    const els = buildUI();

    els.fab.addEventListener("click", () => openModal(els));
    els.closeBtn.addEventListener("click", () => closeModal(els));
    els.backdrop.addEventListener("click", (e) => {
      if (e.target === els.backdrop) closeModal(els);
    });
    els.submit.addEventListener("click", () => submitJob(els));
    els.textarea.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        submitJob(els);
      }
    });
    els.refreshBtn.addEventListener("click", () => window.location.reload());
    els.undoBtn.addEventListener("click", () => submitUndo(els));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

### Verify

1. **File existence**:
   ```bash
   ls -la static/ops.css static/ops.js
   # Both files should exist
   ```

2. **Manual browser test** — run Forge with all extensions enabled against the demo vault:
   ```bash
   ./forge dev --input /path/to/demo/vault --output /tmp/forge-test --port 9090 \
     --overlay-dir ./static --inject-overlay
   ```
   Open `http://localhost:9090` in a browser. Verify:
   - [ ] The `*` FAB button appears in the bottom-right corner.
   - [ ] Clicking the FAB opens the modal with a textarea and "Run" button.
   - [ ] The page path is displayed in the modal header.
   - [ ] The close button (×) closes the modal.
   - [ ] Clicking the backdrop outside the modal closes it.
   - [ ] The textarea is focusable and accepts input.
   - [ ] View page source: the `<!-- ops-overlay -->` marker, CSS link, and JS script tag appear before `</head>`.

3. **JS behavior with mock backend** — start the mock backend from Step 5, then:
   - Type an instruction and click Run → modal should show "Working..." then display the mock response.
   - Click Undo → should send POST to `/api/undo` and display the result.
   - Click Refresh → page reloads.

---

## Step 7: Write integration tests

### What to do

Create `internal/server/forge_test.go` that tests the full handler chain end-to-end using `httptest.Server`:

```go
package server_test

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"YOUR_MODULE/internal/overlay"
	"YOUR_MODULE/internal/proxy"
	"YOUR_MODULE/internal/server"
)

func setupTestForge(t *testing.T) (*httptest.Server, *httptest.Server) {
	t.Helper()

	// Create a mock backend
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		w.Write([]byte(`{"status":"ok","path":"` + r.URL.Path + `"}`))
	}))

	// Create overlay dir
	overlayDir := t.TempDir()
	os.WriteFile(filepath.Join(overlayDir, "ops.css"), []byte("body{}"), 0644)
	os.WriteFile(filepath.Join(overlayDir, "ops.js"), []byte("console.log('ok')"), 0644)

	// Create a site dir with HTML
	siteDir := t.TempDir()
	os.WriteFile(filepath.Join(siteDir, "index.html"), []byte(`<!DOCTYPE html>
<html><head><title>Test</title></head><body><p>Hello</p></body></html>`), 0644)
	os.MkdirAll(filepath.Join(siteDir, "notes"), 0755)
	os.WriteFile(filepath.Join(siteDir, "notes", "example.html"), []byte(`<!DOCTYPE html>
<html><head><title>Note</title></head><body><p>Note content</p></body></html>`), 0644)

	// Build handler chain
	baseHandler := http.FileServer(http.Dir(siteDir))
	proxyHandler, _ := proxy.NewReverseProxy(backend.URL)
	overlayHandler := overlay.NewStaticHandler(overlayDir)

	forgeHandler := server.NewForgeHandler(baseHandler, server.ForgeConfig{
		ProxyHandler:   proxyHandler,
		OverlayHandler: overlayHandler,
		InjectEnabled:  true,
	})

	forgeServer := httptest.NewServer(forgeHandler)
	return forgeServer, backend
}

func TestForge_APIProxied(t *testing.T) {
	forge, backend := setupTestForge(t)
	defer forge.Close()
	defer backend.Close()

	resp, err := http.Get(forge.URL + "/api/health")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"/api/health"`) {
		t.Fatalf("proxy did not forward path: %s", body)
	}
}

func TestForge_OverlayServed(t *testing.T) {
	forge, backend := setupTestForge(t)
	defer forge.Close()
	defer backend.Close()

	resp, err := http.Get(forge.URL + "/ops/ops.css")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if string(body) != "body{}" {
		t.Fatalf("unexpected overlay content: %s", body)
	}
}

func TestForge_HTMLInjected(t *testing.T) {
	forge, backend := setupTestForge(t)
	defer forge.Close()
	defer backend.Close()

	resp, err := http.Get(forge.URL + "/index.html")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "ops-overlay") {
		t.Fatalf("injection not found in HTML: %s", body)
	}
	if !strings.Contains(string(body), "ops.css") {
		t.Fatal("CSS link not injected")
	}
	if !strings.Contains(string(body), "ops.js") {
		t.Fatal("JS script not injected")
	}
}

func TestForge_NonHTMLNotInjected(t *testing.T) {
	forge, backend := setupTestForge(t)
	defer forge.Close()
	defer backend.Close()

	resp, err := http.Get(forge.URL + "/ops/ops.css")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if strings.Contains(string(body), "ops-overlay") {
		t.Fatal("CSS file should not be injected")
	}
}

func TestForge_APINotInjected(t *testing.T) {
	forge, backend := setupTestForge(t)
	defer forge.Close()
	defer backend.Close()

	resp, err := http.Get(forge.URL + "/api/health")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if strings.Contains(string(body), "ops-overlay") {
		t.Fatal("API responses should not be injected")
	}
}
```

### Verify

```bash
go test ./internal/server/ -v -run TestForge
go test ./... -v  # Run ALL tests across all packages
```

All tests must pass with zero failures.

---

## Step 8: Add a `--proxy-timeout` flag (optional hardening)

### What to do

Add a `--proxy-timeout` flag to the dev command (default: `180`). Pass this to `proxy.NewReverseProxy` so the timeout is configurable rather than hardcoded.

Update `internal/proxy/reverse.go`:

```go
func NewReverseProxy(backendURL string, timeout time.Duration) (http.Handler, error) {
    // ... same as before, but use `timeout` instead of 180*time.Second
}
```

Update the dev command and all test callsites.

### Verify

```bash
go test ./internal/proxy/ -v
go test ./... -v
go build ./cmd/forge
./forge dev --help | grep proxy-timeout
```

---

## Step 9: Final cleanup and documentation

### What to do

1. **Update the forge README** (or create one) with:
   - What Forge is (a Kiln fork with overlay, proxy, and injection capabilities).
   - The new CLI flags and their purpose.
   - Usage examples showing Forge as a plain Kiln replacement and with all extensions.

2. **Clean up unused Kiln code** if any (e.g., `cmd/kiln-palette/` if not needed). Do NOT remove core Kiln functionality.

3. **Verify the `flake.nix`** builds correctly if the project uses Nix:
   ```bash
   nix build  # Should produce the forge binary
   ```

4. **Tag the release**: Once all tests pass and manual verification is complete, tag as `v0.1.0`.

### Final verification checklist

Run through this complete checklist before declaring Forge done:

```bash
# Build
go build ./cmd/forge

# All tests
go test ./... -v

# Linting
go vet ./...
```

**Manual tests** (each must pass):

| # | Test | Expected result |
|---|------|-----------------|
| 1 | `forge dev --input vault --output site --port 9090` (no extensions) | Site renders exactly like `kiln dev`. No overlay. |
| 2 | Add `--overlay-dir ./static` | `/ops/ops.css` and `/ops/ops.js` return file contents. |
| 3 | Add `--inject-overlay` | HTML pages contain `<!-- ops-overlay -->`, CSS link, JS script before `</head>`. |
| 4 | Add `--proxy-backend http://127.0.0.1:8081` with mock backend running | `/api/health` returns backend response. `POST /api/apply` forwards body and returns response. |
| 5 | All three flags together | All behaviors work simultaneously without interference. |
| 6 | HTML page with no `</head>` tag | Page renders without injection, no errors. |
| 7 | Binary files (images, fonts) served from site | Pass through without corruption. |
| 8 | Backend is down, request `/api/apply` | Returns 502 Bad Gateway. |
| 9 | Request to `/ops/nonexistent.txt` | Returns 404. |
| 10 | Browser: click FAB, type instruction, submit | Modal opens, instruction sent, response displayed. |

---

## Summary of deliverables

| File | Purpose |
|------|---------|
| `internal/overlay/static.go` | `/ops/*` static file serving |
| `internal/overlay/static_test.go` | Tests for static serving |
| `internal/overlay/inject.go` | HTML injection middleware |
| `internal/overlay/inject_test.go` | Tests for injection |
| `internal/proxy/reverse.go` | `/api/*` reverse proxy |
| `internal/proxy/reverse_test.go` | Tests for reverse proxy |
| `internal/server/mux.go` | Handler chain composition |
| `internal/server/forge_test.go` | Integration tests |
| `static/ops.css` | Overlay stylesheet (copied from obsidian-ops) |
| `static/ops.js` | Overlay JavaScript (simplified, no SSE) |

**New Go code**: ~150 lines of production code, ~350 lines of test code.

**Modified Kiln code**: CLI flag registration (~10 lines) and server setup integration (~20 lines). All Kiln core code remains untouched.
